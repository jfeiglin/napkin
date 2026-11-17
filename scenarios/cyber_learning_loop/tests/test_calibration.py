"""The scenario's totals of today, built from its stages, against the ranges that the evidence gives.

The model's inputs describe single kinds of work. Today's work of an attack, the attacks of a year and
the time to build an attack are results, so they can disagree with what the evidence shows. These tests
compare them with evidence ranges that are frozen here, never with the model's own defaults. A failing
test is a finding about the inputs or the evidence, to report, not a value to tune.

The ranges:
- work of one attack today, 8.1 to 15.3 expert-years: the staff of the access program (1,870) and the
  attack-oriented posts (3,535) over about 231 offensive operations in 2011 (research notes, costs);
- attacks a year today, 231 to 437: the operations of 2011, and the attack posts over the lower work;
- time to build an attack today, 2 to 11 months: first known access before the effect in six documented
  operations (research notes, effects chain);
- share of the tactical work that AI does at the end of AI progress, 0.8 to 0.9: one AI-orchestrated
  espionage campaign, for the stages that its work covers (access and the running of the operation);
- chance of attribution today, 0.6 to 0.95: technical attribution of significant attacks."""

from __future__ import annotations

from napkin.core import expr
from napkin.dynamics import vector_field
from tests.helpers import catalogue_model

YEAR_H = 8760.0
TACTICAL = ('access_stage', 'execution_stage')


def values_at(run, names, t_years=0.0, values=None):
    field = vector_field(catalogue_model('cyber_learning_loop'), run, values)
    program = field.field.values_program([expr.ref(name) for name in names])
    return dict(zip(names, program(t_years * YEAR_H, field.base)))


def today(names):
    return values_at('no_ai', names)


def test_the_work_of_an_attack_today_is_in_the_range_of_the_evidence():
    work = today(['effects_program.cost_now'])['effects_program.cost_now'] / YEAR_H
    assert 8.1 <= work <= 15.3


def test_the_attacks_of_a_year_today_are_in_the_range_of_the_evidence():
    attacks = today(['effects_program.attacks_now'])['effects_program.attacks_now'] * YEAR_H
    assert 231 <= attacks <= 437


def test_the_time_to_build_an_attack_today_is_in_the_range_of_the_evidence():
    months = today(['effects_program.lead_now'])['effects_program.lead_now'] / YEAR_H * 12
    assert 2 <= months <= 11


def test_ai_does_the_share_of_the_tactical_work_that_an_ai_campaign_showed():
    names = [f'{s}.{m}' for s in TACTICAL for m in ('ai_work', 'hand_work')]
    v = values_at('ai_fast', names, 60)
    share = sum(v[f'{s}.ai_work'] for s in TACTICAL) / sum(v[f'{s}.hand_work'] for s in TACTICAL)
    assert 0.8 <= share <= 0.9


def test_the_chance_of_attribution_today_is_in_the_range_of_the_evidence():
    # Technical attribution of significant attacks: about 0.6 to 0.95; every large destructive state attack
    # of recent years was attributed (research notes, politics).
    chance = today(['other_states.attribution_now'])['other_states.attribution_now']
    assert 0.6 <= chance <= 0.95
