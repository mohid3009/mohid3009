"""GitHub stats via the GraphQL API.

Token lookup: $GITHUB_TOKEN / $GH_TOKEN (GitHub Actions secret), else the local
`gh auth token`. The token is only ever sent to api.github.com; it is never
printed or written. Results are cached in data/github.json (public numbers
only) so rendering works offline. With neither a token nor a cache, stats are
None and the HUD says so; nothing is ever made up.
"""
import json
import os
import subprocess
import urllib.request
from datetime import date

QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes { stargazerCount primaryLanguage { name } }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def _token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "catopia"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors") or not body.get("data", {}).get("user"):
        raise RuntimeError(f"GitHub API error: {body.get('errors', 'user not found')}")
    return body["data"]["user"]


def summarize(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [(d["date"], d["contributionCount"]) for w in cal["weeks"] for d in w["contributionDays"]]
    counts = [c for _, c in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    tail = counts[:-1] if counts and counts[-1] == 0 else counts  # today may not be over yet
    current = 0
    for c in reversed(tail):
        if not c:
            break
        current += 1
    repos = user["repositories"]
    langs = {}
    for r in repos["nodes"]:
        if r["primaryLanguage"]:
            langs[r["primaryLanguage"]["name"]] = langs.get(r["primaryLanguage"]["name"], 0) + 1
    return {
        "login": user["login"],
        "fetched": date.today().isoformat(),
        "total": cal["totalContributions"],
        "last7": sum(counts[-7:]),
        "current_streak": current,
        "longest_streak": longest,
        "repos": repos["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos["nodes"]),
        "top_language": max(langs, key=langs.get) if langs else None,
        "days": days,
    }


def load(login, cache="data/github.json", refresh=True):
    token = _token() if refresh else None
    if token:
        try:
            stats = summarize(fetch(login, token))
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w") as f:
                json.dump(stats, f)
            return stats
        except Exception as e:  # network/API trouble: fall back to the cache
            print(f"github: fetch failed ({type(e).__name__}), using cache")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    # self-check of the streak logic on synthetic data
    wk = lambda cs: {"contributionDays": [{"date": f"d{i}", "contributionCount": c} for i, c in enumerate(cs)]}
    user = {"login": "t", "repositories": {"totalCount": 0, "nodes": []},
            "contributionsCollection": {"contributionCalendar": {"totalContributions": 9,
                                                                 "weeks": [wk([1, 1, 1, 0, 2, 2, 0])]}}}
    s = summarize(user)
    assert (s["current_streak"], s["longest_streak"], s["last7"]) == (2, 3, 7), s
    print("ok")
