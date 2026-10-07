import unittest

from radar.models import Job
from radar.scoring import evaluate


RJ = ["rio de janeiro", "nova iguaçu", "mesquita"]


class ScoringTests(unittest.TestCase):
    def test_remote_power_bi_is_priority(self):
        job = Job(
            source="test",
            external_id="1",
            title="Analista de Dados - Power BI",
            company="Empresa",
            location="Brasil - Remoto",
            url="https://example.com/1",
            description="Excel, dashboards e indicadores",
            work_mode="remote",
        )
        match = evaluate(job, RJ)
        self.assertFalse(match.rejected)
        self.assertGreaterEqual(match.score, 10)
        self.assertEqual(match.label, "PRIORIDADE")

    def test_senior_title_is_rejected(self):
        job = Job(
            source="test",
            external_id="2",
            title="Senior Data Analyst",
            company="Empresa",
            location="Remote",
            url="https://example.com/2",
        )
        self.assertTrue(evaluate(job, RJ).rejected)

    def test_onsite_outside_rj_is_rejected(self):
        job = Job(
            source="test",
            external_id="3",
            title="Assistente Administrativo",
            company="Empresa",
            location="São Paulo, SP",
            url="https://example.com/3",
            work_mode="onsite",
        )
        self.assertTrue(evaluate(job, RJ).rejected)


if __name__ == "__main__":
    unittest.main()
