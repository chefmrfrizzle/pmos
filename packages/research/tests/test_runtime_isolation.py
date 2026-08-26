from pmos_research.runtime_isolation import sanitized_environment

def test_sanitized_worker_environment_strips_proxies_and_credentials():
    result=sanitized_environment({"PATH":"/bin","HOME":"/Users/worker","LANG":"en","PMOS_DB_URL":"sqlite:///private.db","HTTPS_PROXY":"http://proxy","AWS_SECRET_ACCESS_KEY":"secret","GITHUB_TOKEN":"token","UNRELATED":"value"})
    assert result=={"PATH":"/bin","HOME":"/Users/worker","LANG":"en","PMOS_DB_URL":"sqlite:///private.db"}
