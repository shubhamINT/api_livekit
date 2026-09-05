import unittest

from src.api.mcp_docs import _load_index, get_doc, list_docs, search_docs


class TestMcpDocs(unittest.TestCase):
    def test_index_covers_docs(self):
        index = _load_index()
        self.assertGreater(len(index), 50)
        title, text = index["api/calls/trigger.md"]
        self.assertTrue(title)
        self.assertIn("#", text)

    def test_get_doc_accepts_path_with_and_without_suffix(self):
        with_suffix = get_doc("api/calls/trigger.md")
        without_suffix = get_doc("api/calls/trigger")
        self.assertEqual(with_suffix, without_suffix)
        self.assertIn("api/calls/trigger.md", with_suffix)

    def test_get_doc_rejects_traversal(self):
        for bad in (
            "../pyproject.toml",
            "api/../../pyproject.toml",
            "../../etc/passwd",
        ):
            self.assertIn("outside documentation tree", get_doc(bad))

    def test_get_doc_leading_slash_stays_inside_docs(self):
        # "/etc/passwd" is treated as docs/etc/passwd.md, i.e. simply missing.
        self.assertIn("No page at", get_doc("/etc/passwd"))
        self.assertEqual(
            get_doc("/api/calls/trigger.md"), get_doc("api/calls/trigger.md")
        )

    def test_get_doc_unknown_page(self):
        self.assertIn("No page at", get_doc("api/nope/missing.md"))

    def test_search_finds_relevant_pages(self):
        # limit=10, not the default 8: the ranking is a raw term count, so a long page
        # that merely repeats "call" a lot outranks the short page that is actually
        # about queue status. Widening the window keeps the test about relevance rather
        # than about how much prose the docs happen to contain.
        result = search_docs("outbound call queue status", limit=10)
        self.assertIn("api/calls/queue-status.md", result)
        # Ranked, not arbitrary: the top hit must mention every query word.
        top = result.split("path: ")[1].split(" ")[0]
        title, text = _load_index()[top]
        haystack = f"{title} {text}".lower()
        for term in ("outbound", "call", "queue", "status"):
            self.assertIn(term, haystack, f"{top} missing {term}")

    def test_search_empty_and_miss(self):
        self.assertIn("Empty query", search_docs("   "))
        self.assertIn("No pages match", search_docs("zzzzqqqnotaword"))

    def test_list_docs_lists_sections(self):
        result = list_docs()
        self.assertIn("## api", result)
        self.assertIn("api/calls/trigger.md", result)


if __name__ == "__main__":
    unittest.main()
