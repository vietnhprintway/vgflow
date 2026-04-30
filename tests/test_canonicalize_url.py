import subprocess

def run_canonical(url):
    r = subprocess.run(["python", "scripts/canonicalize_url.py", url],
                       capture_output=True, text=True)
    return r.stdout.strip()

def test_strip_volatile_params():
    assert run_canonical("https://x.com/a?t=12345&id=42") == "https://x.com/a?id=42"
    assert run_canonical("https://x.com/a?session_id=abc&page=2") == "https://x.com/a?page=2"

def test_normalize_trailing_slash():
    expected = "https://x.com/a"
    assert run_canonical("https://x.com/a/") == expected
    assert run_canonical("https://x.com/a") == expected

def test_lowercase_host():
    assert run_canonical("HTTPS://X.COM/A") == "https://x.com/A"

def test_strip_fragment():
    assert run_canonical("https://x.com/a#section") == "https://x.com/a"
