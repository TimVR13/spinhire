import unittest

from server.app import Job


class JobLanguageTests(unittest.TestCase):
    def test_detects_explicit_working_languages(self):
        job = Job(title="German-speaking VIP Manager", tags="English, relocation",
                  description="Fluent German is required for this role")
        self.assertEqual({code for code, _ in job.language_list}, {"de", "en"})

    def test_language_tags_are_not_duplicated_in_regular_tags(self):
        job = Job(title="CRM Lead", tags="English, CRM, relocation", description="")
        self.assertEqual(job.tag_list, ["CRM", "relocation"])


if __name__ == "__main__":
    unittest.main()
