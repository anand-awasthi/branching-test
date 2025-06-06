import os
import re
import json
import requests
from pathlib import Path

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("REPO")
PR_NUMBER = os.getenv("PR_NUMBER")
API_BASE = "https://api.github.com"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}


def find_codeowners_file():
    for path in [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]:
        if Path(path).is_file():
            return Path(path)
    return None


def extract_owners(codeowners_file):
    content = codeowners_file.read_text()
    matches = re.findall(r"@([a-zA-Z0-9_\-/]+)", content)
    return set(m.lower() for m in matches)


def get_team_members(org, team_slug):
    """Returns a set of usernames for a GitHub team"""
    members = set()
    page = 1
    while True:
        url = f"{API_BASE}/orgs/{org}/teams/{team_slug}/members?page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 404:
            print(f"⚠️ Team {org}/{team_slug} not found or no access.")
            break
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        members.update(user["login"].lower() for user in data)
        page += 1
    return members


def resolve_codeowners(raw_owners):
    resolved = set()
    for owner in raw_owners:
        if "/" in owner:  # probably a team
            org, team = owner.split("/", 1)
            resolved.update(get_team_members(org, team))
        else:
            resolved.add(owner)
    return resolved


def get_approvers(repo, pr_number):
    url = f"{API_BASE}/repos/{repo}/pulls/{pr_number}/reviews"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    reviews = r.json()

    # Get latest state per user (ignore dismissed or outdated)
    approvers = {}
    for review in reviews:
        user = review["user"]["login"].lower()
        state = review["state"]
        if state == "APPROVED":
            approvers[user] = state
        elif state in ["CHANGES_REQUESTED", "DISMISSED"]:
            approvers.pop(user, None)  # remove their approval
    return set(approvers.keys())


def main():
    if not all([GITHUB_TOKEN, REPO, PR_NUMBER]):
        print("❌ Missing environment variables.")
        exit(1)

    file = find_codeowners_file()
    if not file:
        print("❌ No CODEOWNERS file found.")
        exit(1)

    print(f"📄 Found CODEOWNERS file at: {file}")
    raw_owners = extract_owners(file)
    print(f"👥 Raw CODEOWNERS: {raw_owners}")

    resolved_owners = resolve_codeowners(raw_owners)
    print(f"✅ Resolved CODEOWNERS (usernames): {resolved_owners}")

    approvers = get_approvers(REPO, PR_NUMBER)
    print(f"📝 PR Approvers: {approvers}")

    matched = resolved_owners & approvers
    print(f"🎯 Matched CODEOWNER approvals: {matched}")

    if len(matched) < 2:
        print(f"❌ Only {len(matched)} CODEOWNER approval(s) found. Minimum 2 required.")
        exit(1)
    else:
        print(f"✅ Passed: {len(matched)} CODEOWNER(s) approved.")


if __name__ == "__main__":
    main()
