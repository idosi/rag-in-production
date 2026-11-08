from rag.evals.red_team import ATTACKS, run_attack
from rag.models import Answer


class FakeGenerator:
    def __init__(self, reply: str):
        self.reply = reply

    def generate(self, question, sources):
        return Answer(text=self.reply, sources=[])


def test_run_attack_fails_when_the_canary_leaks():
    attack = ATTACKS[0]
    gen = FakeGenerator(f"Sure! {attack.canary}")
    assert run_attack(attack, gen) is False


def test_run_attack_passes_when_the_answer_is_clean():
    attack = ATTACKS[0]
    gen = FakeGenerator("Use Optional with a default of None. [1]")
    assert run_attack(attack, gen) is True
