import unittest

from app.database.models import Article, Base, Digest, Source


class DatabaseModelTests(unittest.TestCase):
    def test_expected_tables_are_registered(self) -> None:
        self.assertEqual(
            set(Base.metadata.tables),
            {"sources", "articles", "digests"},
        )

    def test_video_id_is_unique_and_article_belongs_to_source(self) -> None:
        article_table = Article.__table__
        self.assertIn(
            "uq_articles_video_id",
            {constraint.name for constraint in article_table.constraints},
        )
        self.assertEqual(
            {foreign_key.target_fullname for foreign_key in article_table.foreign_keys},
            {"sources.id"},
        )
        self.assertEqual(Source.__tablename__, "sources")

    def test_digest_is_unique_per_utc_run_date(self) -> None:
        digest_table = Digest.__table__
        self.assertIn(
            "uq_digests_run_date",
            {constraint.name for constraint in digest_table.constraints},
        )
        self.assertIn("ck_digests_status", {
            constraint.name for constraint in digest_table.constraints
        })


if __name__ == "__main__":
    unittest.main()
