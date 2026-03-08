"""
github_verifier.py — Verify candidate projects via GitHub API + commit history analysis

Extracts GitHub username from resume links, fetches repos and commit history,
and analyzes whether the work looks legitimate.
"""

import os
import re
import httpx
from difflib import SequenceMatcher
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


def _github_headers() -> dict:
    """Return GitHub API headers, with auth token if available."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def extract_github_username(links: list[str]) -> str | None:
    """Extract GitHub username from a list of URLs."""
    for link in links:
        # Match github.com/<username> (but not github.com/orgs, settings, etc.)
        match = re.match(
            r"https?://(?:www\.)?github\.com/([A-Za-z0-9_-]+)/?$", link
        )
        if match:
            username = match.group(1)
            # Skip common non-user paths
            if username.lower() not in (
                "orgs", "settings", "marketplace", "explore",
                "topics", "trending", "collections", "sponsors",
                "login", "signup", "about", "pricing",
            ):
                return username

    # Also try repo URLs like github.com/<user>/<repo>
    for link in links:
        match = re.match(
            r"https?://(?:www\.)?github\.com/([A-Za-z0-9_-]+)/[A-Za-z0-9_.-]+", link
        )
        if match:
            username = match.group(1)
            if username.lower() not in (
                "orgs", "settings", "marketplace", "explore",
            ):
                return username

    return None


async def fetch_github_repos(username: str) -> list[dict]:
    """Fetch all public repos for a GitHub user."""
    repos = []
    page = 1
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            resp = await client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
                headers=_github_headers(),
            )
            if resp.status_code != 200:
                print(f"[github] API error {resp.status_code}: {resp.text[:200]}")
                break
            batch = resp.json()
            if not batch:
                break
            for r in batch:
                repos.append({
                    "name": r.get("name", ""),
                    "full_name": r.get("full_name", ""),
                    "description": r.get("description") or "",
                    "language": r.get("language") or "",
                    "stars": r.get("stargazers_count", 0),
                    "forks": r.get("forks_count", 0),
                    "created_at": r.get("created_at", ""),
                    "updated_at": r.get("updated_at", ""),
                    "fork": r.get("fork", False),
                })
            page += 1
            if len(batch) < 100:
                break
    return repos


async def fetch_contributed_repos(username: str) -> list[dict]:
    """
    Find repos where the user has committed but doesn't own.
    Uses GitHub Search API to find commits by the user across all public repos.
    Returns list of repos with owner info and user's commit count.
    """
    contributed = {}
    async with httpx.AsyncClient(timeout=20) as client:
        # Search for commits authored by this user
        resp = await client.get(
            "https://api.github.com/search/commits",
            params={"q": f"author:{username}", "sort": "author-date", "per_page": 100},
            headers={**_github_headers(), "Accept": "application/vnd.github.cloak-preview+json"},
        )
        if resp.status_code != 200:
            print(f"[github] Search API error {resp.status_code}: {resp.text[:200]}")
            return []

        items = resp.json().get("items", [])
        for item in items:
            repo_info = item.get("repository", {})
            full_name = repo_info.get("full_name", "")
            owner = full_name.split("/")[0] if "/" in full_name else ""

            # Skip repos owned by the user (already fetched separately)
            if owner.lower() == username.lower():
                continue

            if full_name not in contributed:
                contributed[full_name] = {
                    "name": repo_info.get("name", ""),
                    "full_name": full_name,
                    "owner": owner,
                    "description": repo_info.get("description") or "",
                    "language": "",
                    "stars": 0,
                    "forks": 0,
                    "fork": False,
                    "created_at": "",
                    "updated_at": "",
                    "user_commits": 0,
                    "is_contribution": True,
                }
            contributed[full_name]["user_commits"] += 1

    result = list(contributed.values())
    if result:
        print(f"[github] Found {len(result)} contributed repos for {username}")
        for r in result:
            print(f"  -> {r['full_name']} ({r['user_commits']} commits)")
    return result


async def fetch_commit_history(username: str, repo_name: str, max_pages: int = 3) -> list[dict]:
    """Fetch recent commit history for a repo."""
    commits = []
    async with httpx.AsyncClient(timeout=15) as client:
        for page in range(1, max_pages + 1):
            resp = await client.get(
                f"https://api.github.com/repos/{username}/{repo_name}/commits",
                params={"per_page": 100, "page": page},
                headers=_github_headers(),
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            for c in batch:
                commit_data = c.get("commit", {})
                author_info = commit_data.get("author", {})
                commits.append({
                    "message": commit_data.get("message", ""),
                    "date": author_info.get("date", ""),
                    "author_name": author_info.get("name", ""),
                    "author_login": (c.get("author") or {}).get("login", ""),
                })
            if len(batch) < 100:
                break
    return commits


async def fetch_repo_text_content(username: str, repo_name: str) -> str:
    """
    Fetch text content from a repo by scanning its file tree.
    Reads README, config files, and other text files to build a keyword corpus.
    """
    import base64

    TEXT_EXTENSIONS = {
        ".md", ".txt", ".rst", ".py", ".js", ".ts", ".jsx", ".tsx",
        ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".cfg",
        ".ini", ".xml", ".csv", ".env.example", ".sh", ".bat",
        ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php",
        ".swift", ".kt", ".scala", ".r", ".m", ".sol",
    }
    # Priority files that contain project metadata — check these first
    PRIORITY_FILES = {
        "readme.md", "readme.txt", "readme.rst", "readme",
        "package.json", "setup.py", "setup.cfg", "pyproject.toml",
        "requirements.txt", "cargo.toml", "pom.xml", "build.gradle",
        "gemfile", "composer.json", "go.mod", "pubspec.yaml",
        "makefile", "dockerfile", "docker-compose.yml",
        "index.html", "app.py", "main.py", "index.js", "app.js",
    }
    MAX_FILES = 8
    MAX_CONTENT = 5000  # total characters cap

    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: Get the default branch SHA
        resp = await client.get(
            f"https://api.github.com/repos/{username}/{repo_name}",
            headers=_github_headers(),
        )
        if resp.status_code != 200:
            return ""
        default_branch = resp.json().get("default_branch", "main")

        # Step 2: Get full file tree
        resp = await client.get(
            f"https://api.github.com/repos/{username}/{repo_name}/git/trees/{default_branch}",
            params={"recursive": "1"},
            headers=_github_headers(),
        )
        if resp.status_code != 200:
            return ""

        tree = resp.json().get("tree", [])

        # Step 3: Identify text files to fetch
        priority = []
        secondary = []
        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            basename = path.rsplit("/", 1)[-1].lower()
            ext = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
            size = item.get("size", 0)

            # Skip huge files
            if size > 50000:
                continue

            if basename in PRIORITY_FILES:
                priority.append(item)
            elif ext in TEXT_EXTENSIONS and size < 20000:
                secondary.append(item)

        # Combine: priority first, then secondary, capped
        files_to_read = (priority + secondary)[:MAX_FILES]

        # Step 4: Fetch file contents
        all_text = []
        total_chars = 0
        for f in files_to_read:
            if total_chars >= MAX_CONTENT:
                break
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{username}/{repo_name}/contents/{f['path']}",
                    headers=_github_headers(),
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="ignore")
                # Cap each file
                remaining = MAX_CONTENT - total_chars
                chunk = content[:remaining]
                all_text.append(chunk)
                total_chars += len(chunk)
            except Exception:
                continue

    return "\n".join(all_text)


async def _fetch_readme_fast(username: str, repo_name: str) -> str:
    """Fast README fetch — single API call using the dedicated endpoint."""
    import base64
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{username}/{repo_name}/readme",
            headers=_github_headers(),
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        try:
            content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="ignore")
            return content[:4000]
        except Exception:
            return ""


def analyze_commit_legitimacy(commits: list[dict], github_username: str) -> dict:
    """
    Analyze commit history to determine if the work looks legitimate.
    Returns legitimacy_score (0-100) and flags.
    """
    if not commits:
        return {
            "legitimacy_score": 0,
            "commit_count": 0,
            "time_span_days": 0,
            "flags": ["No commits found — project may be empty or private"],
            "verdict": "no_data",
        }

    commit_count = len(commits)
    flags = []
    score = 50  # Start at neutral

    # --- 1. Parse dates ---
    dates = []
    for c in commits:
        try:
            dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
            dates.append(dt)
        except (ValueError, KeyError):
            pass

    dates.sort()

    # --- 2. Time span ---
    time_span_days = 0
    if len(dates) >= 2:
        time_span_days = (dates[-1] - dates[0]).days

    # --- 3. Commit count scoring ---
    if commit_count >= 20:
        score += 15
        flags.append(f"Good commit volume ({commit_count} commits)")
    elif commit_count >= 5:
        score += 5
        flags.append(f"Moderate commit count ({commit_count})")
    else:
        score -= 15
        flags.append(f"Very few commits ({commit_count}) — possibly rushed or faked")

    # --- 4. Time span scoring ---
    if time_span_days >= 30:
        score += 15
        flags.append(f"Work spans {time_span_days} days — looks like sustained effort")
    elif time_span_days >= 7:
        score += 5
        flags.append(f"Work spans {time_span_days} days")
    elif time_span_days <= 1 and commit_count > 5:
        score -= 20
        flags.append(f"All {commit_count} commits in 1 day — likely bulk upload or faked")
    elif time_span_days <= 3 and commit_count > 10:
        score -= 10
        flags.append(f"{commit_count} commits crammed into {time_span_days} days — suspicious")

    # --- 5. Commit message quality ---
    generic_msgs = {"initial commit", "update", "fix", ".", "commit", "changes",
                     "first commit", "init", "add files", "uploaded"}
    generic_count = sum(
        1 for c in commits
        if c["message"].strip().lower().split("\n")[0] in generic_msgs
    )
    if generic_count > commit_count * 0.6 and commit_count > 3:
        score -= 15
        flags.append(f"{generic_count}/{commit_count} commits have generic messages — low effort")
    elif generic_count <= commit_count * 0.3:
        score += 10
        flags.append("Good commit message quality")

    # --- 6. Author consistency ---
    user_lower = github_username.lower()
    user_commits = sum(
        1 for c in commits
        if c.get("author_login", "").lower() == user_lower
        or user_lower in c.get("author_name", "").lower()
    )
    if commit_count > 0:
        user_ratio = user_commits / commit_count
        if user_ratio >= 0.8:
            score += 10
            flags.append(f"Candidate authored {user_commits}/{commit_count} commits")
        elif user_ratio >= 0.5:
            score += 0
            flags.append(f"Candidate authored {user_commits}/{commit_count} commits — some by others")
        elif user_ratio < 0.3 and commit_count > 3:
            score -= 15
            flags.append(f"Candidate only authored {user_commits}/{commit_count} commits — may not be their work")

    # Clamp score
    score = max(0, min(100, score))

    # Overall verdict
    if score >= 70:
        verdict = "legitimate"
    elif score >= 40:
        verdict = "uncertain"
    else:
        verdict = "suspicious"

    return {
        "legitimacy_score": score,
        "commit_count": commit_count,
        "time_span_days": time_span_days,
        "flags": flags,
        "verdict": verdict,
    }



def _similarity(a: str, b: str) -> float:
    """Fuzzy string similarity (0-1)."""
    a = re.sub(r"[^a-z0-9]", "", a.lower())
    b = re.sub(r"[^a-z0-9]", "", b.lower())
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b).ratio()


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords (3+ chars) from text."""
    words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
    stop = {"the", "and", "for", "with", "using", "from", "that", "this",
            "are", "was", "were", "been", "have", "has", "had", "not",
            "but", "can", "will", "our", "its", "all", "any", "each",
            "project", "based", "app", "application", "built"}
    return {w for w in words if len(w) >= 3 and w not in stop}


def _substring_match_count(project_kws: set[str], text: str) -> int:
    """Count how many project keywords appear as substrings in the text.
    Also checks if text words are substrings of project keywords (bidirectional)."""
    text_lower = re.sub(r"[-_.]", " ", text.lower())
    text_flat = text_lower.replace(" ", "")  # e.g. 'hack105' stays as-is
    count = 0
    for kw in project_kws:
        if len(kw) < 3:
            continue
        # Check: keyword in text (exact or as substring)
        if kw in text_lower or kw in text_flat:
            count += 1
        else:
            # Check if any word in text contains this keyword
            for word in text_lower.split():
                if len(word) >= 3 and (kw in word or word in kw):
                    count += 1
                    break
    return count


def _keyword_overlap(keywords_a: set[str], keywords_b: set[str]) -> float:
    """Compute keyword overlap score (0-1), including substring matches."""
    if not keywords_a or not keywords_b:
        return 0
    # Exact matches
    matches = len(keywords_a & keywords_b)
    # Substring matches (for words not already matched exactly)
    remaining_a = keywords_a - keywords_b
    remaining_b = keywords_b - keywords_a
    for kw_a in remaining_a:
        if len(kw_a) < 3:
            continue
        for kw_b in remaining_b:
            if len(kw_b) < 3:
                continue
            if kw_a in kw_b or kw_b in kw_a:
                matches += 0.7  # partial credit for substring match
                break
    smaller = min(len(keywords_a), len(keywords_b))
    return matches / smaller if smaller > 0 else 0


async def match_project_to_repo(
    project_name: str,
    project_desc: str,
    project_techs: list[str],
    repos: list[dict],
    github_username: str,
    threshold: float = 0.2,
) -> dict | None:
    """
    Find the best matching GitHub repo for a resume project.
    Uses multi-signal matching: name, description, keywords, techs, and README.
    """
    # Build keyword sets
    project_text = f"{project_name} {project_desc} {' '.join(project_techs)}"
    project_kws = _extract_keywords(project_text)
    name_kws = _extract_keywords(project_name)
    desc_kws = _extract_keywords(project_desc) if project_desc else set()
    tech_kws = {t.lower().strip() for t in project_techs if len(t.strip()) >= 2}
    all_project_kws = project_kws | name_kws | desc_kws | tech_kws

    best_match = None
    best_score = 0.0
    repo_scores = []  # track scores for README fallback sorting

    for repo in repos:
        score = 0.0
        repo_name_clean = re.sub(r"[-_.]", " ", repo["name"].lower())
        repo_name_kws = _extract_keywords(repo["name"])
        repo_desc_kws = _extract_keywords(repo.get("description", ""))
        repo_all_kws = repo_name_kws | repo_desc_kws

        # 1. Name similarity (fuzzy)
        name_sim = _similarity(project_name, repo["name"])
        score += name_sim * 0.25

        # 2. Individual keyword hits (substring-aware) in repo name + description
        #    e.g. "hack" matches "hack105", "image" matches "imageprocessing"
        repo_searchable = f"{repo['name']} {repo.get('description', '')}"
        matching_words = _substring_match_count(all_project_kws, repo_searchable)
        if len(all_project_kws) > 0:
            word_hit_ratio = matching_words / len(all_project_kws)
            score += word_hit_ratio * 0.35  # 35% weight — most important signal

        # 3. Full keyword set overlap
        full_overlap = _keyword_overlap(all_project_kws, repo_all_kws)
        score += full_overlap * 0.2

        # 4. Technology / language match
        repo_lang = repo.get("language", "").lower()
        if repo_lang and repo_lang in tech_kws:
            score += 0.1

        # 5. Description keyword overlap specifically
        if desc_kws and repo_desc_kws:
            desc_overlap = _keyword_overlap(desc_kws, repo_desc_kws)
            score += desc_overlap * 0.1

        repo_scores.append((repo, score))
        if score > best_score and score >= threshold:
            best_score = score
            best_match = repo
            print(f"[github] Match: '{project_name}' → '{repo['name']}' score={score:.2f}")

    # README fallback: sort by KEYWORD OVERLAP score (not name similarity)
    if best_score < 0.45:
        # Sort repos by their keyword score, check top 5 READMEs
        repo_scores.sort(key=lambda x: x[1], reverse=True)
        candidates = [r for r, s in repo_scores[:5]]

        for repo in candidates:
            try:
                # Deep scan: check ALL text files in the repo, not just README
                owner = repo.get("owner", github_username)
                repo_content = await fetch_repo_text_content(owner, repo["name"])
                if not repo_content:
                    # Fall back to fast README
                    repo_content = await _fetch_readme_fast(owner, repo["name"])
                if not repo_content:
                    continue
                content_kws = _extract_keywords(repo_content)
                content_lower = repo_content.lower()

                overlap = _keyword_overlap(all_project_kws, content_kws)
                tech_matches = sum(1 for t in project_techs if t.lower() in content_lower)
                tech_bonus = min(tech_matches * 0.1, 0.3)

                name_hits = _substring_match_count(name_kws, repo_content)
                name_bonus = (name_hits / max(len(name_kws), 1)) * 0.2

                total = overlap * 0.4 + tech_bonus + name_bonus + _similarity(project_name, repo["name"]) * 0.1
                print(f"[github] Deep scan: '{project_name}' vs '{repo.get('full_name', repo['name'])}' = {total:.2f} (overlap={overlap:.2f})")

                if total > best_score and total >= threshold:
                    best_score = total
                    best_match = repo
            except Exception as e:
                print(f"[github] Deep scan error for {repo['name']}: {e}")
                continue

    return best_match


def check_transcript_mentions(project_name: str, transcript_text: str) -> bool:
    """Check if a project name (or close variant) is mentioned in the transcript."""
    if not transcript_text:
        return False
    # Normalize
    name_lower = project_name.lower()
    text_lower = transcript_text.lower()
    # Direct mention
    if name_lower in text_lower:
        return True
    # Also check without common separators (e.g., "my-app" → "my app" → "myapp")
    name_clean = re.sub(r"[-_.]", " ", name_lower)
    if name_clean in text_lower:
        return True
    name_no_space = re.sub(r"[-_.\s]", "", name_lower)
    text_no_space = re.sub(r"[-_.\s]", "", text_lower)
    if len(name_no_space) > 3 and name_no_space in text_no_space:
        return True
    return False


async def verify_projects(
    projects: list[dict],
    github_username: str,
    transcript_text: str = "",
) -> dict:
    """
    Full verification pipeline:
    1. Fetch repos
    2. Match each resume project to a repo
    3. Fetch commit history for matched repos
    4. Analyze legitimacy
    5. Check transcript mentions
    """
    # Step 1: Fetch owned repos
    repos = await fetch_github_repos(github_username)

    # Step 1b: Fetch repos where user has contributed (other users' repos)
    contributed = await fetch_contributed_repos(github_username)
    all_repos = repos + contributed

    if not all_repos:
        return {
            "github_username": github_username,
            "repos_found": 0,
            "projects": [{
                "project_name": p.get("name", "Unknown"),
                "repo_found": False,
                "mentioned_in_transcript": check_transcript_mentions(
                    p.get("name", ""), transcript_text
                ),
                "commit_count": 0,
                "time_span_days": 0,
                "legitimacy_score": 0,
                "legitimacy_flags": ["No public repos found for this user"],
                "verdict": "not_found",
            } for p in projects],
        }

    results = []
    used_repos = set()  # prevent same repo matching multiple projects

    for project in projects:
        project_name = project.get("name", "")
        project_desc = project.get("description", "") or ""
        project_techs = project.get("technologies", []) or []
        
        # Filter out already-matched repos
        available_repos = [r for r in all_repos if r["name"] not in used_repos]

        # Step 2: Match to repo
        matched_repo = await match_project_to_repo(
            project_name, project_desc, project_techs,
            available_repos, github_username,
        )
        mentioned = check_transcript_mentions(project_name, transcript_text)

        if not matched_repo:
            results.append({
                "project_name": project_name,
                "github_repo": None,
                "repo_found": False,
                "mentioned_in_transcript": mentioned,
                "commit_count": 0,
                "time_span_days": 0,
                "legitimacy_score": 0,
                "legitimacy_flags": ["No matching repo found on GitHub"],
                "verdict": "not_found",
            })
            continue

        # Mark repo as used
        used_repos.add(matched_repo["name"])

        # Step 3: Fetch commit history (handle cross-user repos)
        repo_owner = matched_repo.get("owner", github_username)
        commits = await fetch_commit_history(repo_owner, matched_repo["name"])

        # Step 4: Analyze legitimacy
        analysis = analyze_commit_legitimacy(commits, github_username)

        # For contributed repos, boost score if user has substantial commits
        is_contribution = matched_repo.get("is_contribution", False)
        contribution_note = ""
        if is_contribution:
            user_commit_count = matched_repo.get("user_commits", 0)
            contribution_note = f"Contributed to {repo_owner}'s repo ({user_commit_count} commits found)"
            # Boost score based on contribution
            if user_commit_count >= 10:
                analysis["legitimacy_score"] = min(100, analysis["legitimacy_score"] + 20)
                analysis["flags"].append(f"Major contributor — {user_commit_count} commits to {repo_owner}/{matched_repo['name']}")
            elif user_commit_count >= 3:
                analysis["legitimacy_score"] = min(100, analysis["legitimacy_score"] + 10)
                analysis["flags"].append(f"Active contributor — {user_commit_count} commits to {repo_owner}/{matched_repo['name']}")
            else:
                analysis["flags"].append(f"Minor contributor — {user_commit_count} commits to {repo_owner}/{matched_repo['name']}")

        # Step 5: Determine final verdict
        if analysis["legitimacy_score"] >= 50 and mentioned:
            verdict = "verified"
        elif analysis["legitimacy_score"] >= 50:
            verdict = "repo_legitimate"
        elif matched_repo and mentioned:
            verdict = "mentioned_but_suspicious"
        else:
            verdict = analysis["verdict"]

        repo_display = f"{repo_owner}/{matched_repo['name']}" if is_contribution else matched_repo["name"]
        results.append({
            "project_name": project_name,
            "github_repo": repo_display,
            "repo_url": f"https://github.com/{repo_owner}/{matched_repo['name']}",
            "repo_found": True,
            "repo_is_fork": matched_repo.get("fork", False),
            "repo_language": matched_repo.get("language", ""),
            "repo_stars": matched_repo.get("stars", 0),
            "mentioned_in_transcript": mentioned,
            "is_contribution": is_contribution,
            "commit_count": analysis["commit_count"],
            "time_span_days": analysis["time_span_days"],
            "legitimacy_score": analysis["legitimacy_score"],
            "legitimacy_flags": analysis["flags"],
            "verdict": verdict,
        })

    return {
        "github_username": github_username,
        "github_profile_url": f"https://github.com/{github_username}",
        "repos_found": len(repos),
        "contributed_repos_found": len(contributed),
        "projects": results,
    }
