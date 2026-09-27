"""Read the exact recruitment vocabulary from the pinned MAA release."""

import json
from functools import lru_cache

from workspace import RELEASE

CLIENTS = {
    "zh-CN": "Official", "zh-TW": "txwy", "en": "YoStarEN",
    "ja": "YoStarJP", "ko": "YoStarKR",
}


@lru_cache(maxsize=5)
def recruitment_tags(language):
    client = CLIENTS[language]
    relative = ("resource/recruitment.json" if client == "Official"
                else f"resource/global/{client}/resource/recruitment.json")
    document = json.loads((RELEASE / relative).read_text())
    return {document["tags"][tag] for operator in document["operators"] for tag in operator["tags"]}
