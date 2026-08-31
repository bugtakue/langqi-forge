"""Locked public-evaluation identities kept outside the submitted runtime bundle."""

PUBLIC_REQUIREMENT_SHA256 = {
    "github": "a4ba2c2e1bd62091a46384e89a823819a485ab609780ce00ead1490edd881959",
    "sheet": "9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494",
}

PUBLIC_TEST_BUNDLE_SHA256 = {
    "github": "7ee72cbedf9c21c6be087867512c2a6259c16f4cdbf0969f46203c7f3d07ed77",
    "sheet": "afec335ed4d442795b344cd6b67f27bdc28583ed0b5ca13876e5acb3a4778f43",
}

PUBLIC_TEST_COUNTS = {"github": 101, "sheet": 102}

# Canonical (file, spec id/title/location, project id/name) inventories from the
# locked raw Playwright reports. A stats-only or empty report cannot match.
PUBLIC_PLAYWRIGHT_INVENTORY_SHA256 = {
    "github": "e09e33f994430d1d2efe9b89ebc7c60504bcd893afdf7f64601e686f23812118",
    "sheet": "9ef10bed3f46935596d07fddf52ca6ab68a2f690892cd2d881dd8ab65f729d77",
}

# Exact user-message hashes reconstructed from the locked public requirement
# files through planner.requirement_digest + PLANNER_USER_PROMPT_PREFIX.
PUBLIC_PLANNER_USER_PROMPT_SHA256 = {
    "github": "e4ffb7dec1afb4074cf1c9fe8f6e917340d3f70f43db760ddc5658e808f076bd",
    "sheet": "3932d5434b7890b573630b3552c988bd11bd4b8b5799560986893bbb336acef0",
}

PLAYWRIGHT_VERSION = "1.62.1"
PLAYWRIGHT_CLI_SHA256 = (
    "79e23e6a249176295b8490567daa7717448a75866d6ea6f6b296ff3d23305c69"
)
PLAYWRIGHT_RUNTIME_FILE_COUNT = 184
PLAYWRIGHT_RUNTIME_SHA256 = (
    "79989525e1b186199504e4c47854bf481e8fba3b092669144d30c6c10dadd7df"
)
