from app.embedding import embed_text
from app.vector_store import init_collection, upsert_document

KNOWLEDGE_BASE = [
    {
        "id": "cwe-20-description-1",
        "text": "CWE-20 Improper Input Validation occurs when a system fails to validate input or validates it incorrectly, allowing unsafe data to be processed.",
        "source": "CWE-20",
        "section": "description",
        "tags": ["input-validation", "security"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-description-2",
        "text": "Input validation ensures that incoming data conforms to expected formats and constraints before being used by the application.",
        "source": "CWE-20",
        "section": "description",
        "tags": ["input-validation", "data-integrity"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-description-3",
        "text": "Inputs can include raw data such as strings, numbers, and files, as well as metadata like headers, sizes, and structured nested content.",
        "source": "CWE-20",
        "section": "description",
        "tags": ["input-validation", "data-processing"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-description-4",
        "text": "Validation must verify properties such as length, type, syntax, consistency, and adherence to domain-specific rules.",
        "source": "CWE-20",
        "section": "description",
        "tags": ["validation", "data-integrity"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-impact-1",
        "text": "Improper input validation can lead to denial of service through application crashes or excessive consumption of CPU and memory resources.",
        "source": "CWE-20",
        "section": "impact",
        "tags": ["dos", "availability"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-impact-2",
        "text": "Attackers may exploit improper validation to access sensitive data such as files or memory by manipulating resource references.",
        "source": "CWE-20",
        "section": "impact",
        "tags": ["data-leak", "confidentiality"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-impact-3",
        "text": "Malicious input can modify application behavior or execute unauthorized commands, impacting system integrity and control flow.",
        "source": "CWE-20",
        "section": "impact",
        "tags": ["code-execution", "integrity"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-mitigation-1",
        "text": "Use an allowlist validation approach where only known valid inputs are accepted and all others are rejected.",
        "source": "CWE-20",
        "section": "mitigation",
        "tags": ["validation", "best-practice"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-mitigation-2",
        "text": "Validate all input sources including user input, cookies, headers, environment variables, and external system data.",
        "source": "CWE-20",
        "section": "mitigation",
        "tags": ["input-validation", "attack-surface"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-mitigation-3",
        "text": "Perform server-side validation even when client-side validation is implemented, as client checks can be bypassed.",
        "source": "CWE-20",
        "section": "mitigation",
        "tags": ["server-side", "security"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-mitigation-4",
        "text": "Ensure proper canonicalization and decoding of input before validation to prevent bypass techniques such as double encoding.",
        "source": "CWE-20",
        "section": "mitigation",
        "tags": ["encoding", "validation"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-mitigation-5",
        "text": "Convert inputs to expected data types and enforce strict bounds checking to ensure values remain within acceptable ranges.",
        "source": "CWE-20",
        "section": "mitigation",
        "tags": ["type-checking", "validation"],
        "org_id": "global"
    },
    {
        "id": "cwe-20-mitigation-6",
        "text": "Use centralized validation mechanisms or frameworks to ensure consistent and secure handling of input across the application.",
        "source": "CWE-20",
        "section": "mitigation",
        "tags": ["framework", "best-practice"],
        "org_id": "global"
    }
]

def bootstrap():
    init_collection()
    for item in KNOWLEDGE_BASE:
        vector = embed_text(item["text"])
        upsert_document(
            doc_id=item["id"],
            vector=vector,
            payload={
                "text": item["text"],
                "org_id": item.get("org_id"),
                "source": item.get("source"),
                "tags": item.get("tags")
            }
        )

if __name__ == "__main__":
    bootstrap()
