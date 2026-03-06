import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI
from .schema import ResumeProfile

# load .env
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

print("API KEY LOADED:", api_key is not None)

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)

def parse_resume(text):

    prompt = f"""
Extract structured resume information.

Return ONLY JSON in this format:

{{
  "skills": [],
  "projects": [
    {{
      "name": "",
      "technologies": [],
      "description": ""
    }}
  ],
  "experience": []
}}

Resume text:
{text}
"""

    response = client.chat.completions.create(
        model="meta-llama/llama-3-8b-instruct",
        messages=[
            {"role": "system", "content": "You extract structured resume information."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    result = response.choices[0].message.content

    print("LLM RAW OUTPUT:")
    print(result)

    # Extract JSON block
    import re

    match = re.search(r"\{.*\}", result, re.DOTALL)

    if not match:
        raise ValueError("No JSON found in model response")

    json_string = match.group(0)

    parsed_json = json.loads(json_string)

    return ResumeProfile(**parsed_json)