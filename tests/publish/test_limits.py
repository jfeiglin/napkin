"""The limits of a scenario's results that its reviewers state show once on its brief and its methods page."""

from tools.publish import limits


def flagged(*statements):
    """The limitations that a scenario's reviewers state (the note `limitations`)."""
    return [{'id': f'L{i}', 'statement': s} for i, s in enumerate(statements)]


def test_each_limit_is_listed_once_on_one_line_unless_the_page_states_it_already():
    stated = flagged('The rate is\nassumed.', 'Later harm is left out.', 'The rate is assumed.')
    part = limits(stated, 'Summary. Later harm is left out. The end.')
    # The page's own statement is not repeated, and one statement written twice is one limit.
    assert [line for line in part if line.startswith('- ')] == ['- The rate is assumed.']
    assert part[0].startswith('## ') and part[-1] == ''


def test_without_a_limit_left_to_list_a_page_has_no_part_for_them():
    assert limits(flagged(), 'Page.') == []
    assert limits(flagged('Harm\nis left out.'), 'Here harm is left out. Harm is left out.') == []
