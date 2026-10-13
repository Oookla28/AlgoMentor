import itertools
import pytest
from apps.graph.services.algorithm_service import linked_list_steps, next_array, string_steps, queue_steps, stack_steps, generate_steps
from core.exceptions import ValidationError


@pytest.mark.parametrize("values", [[], [1], [1, 2], [1, 2, 2, 4, -1]])
def test_linked_reverse_pointer_invariant(values):
    steps = linked_list_steps(values)
    final = steps[-1]["state"]
    output = []
    current = final["head"]
    seen = set()
    while current is not None:
        assert current not in seen
        seen.add(current)
        output.append(final["values"][current])
        current = final["links"][current]
    assert output == list(reversed(values))
    assert steps[0]["state"]["links"] != final["links"] or len(values) <= 1
    assert [step["step_index"] for step in steps] == list(range(len(steps)))


def test_kmp_next_array_textbook_convention():
    assert next_array("abcac") == [-1, 0, 0, 0, 1]
    assert next_array("aaaa") == [-1, 0, 1, 2]
    assert next_array("") == []


@pytest.mark.parametrize("algorithm", ["kmp", "bf"])
def test_pattern_matching_exhaustive_against_builtin(algorithm):
    strings = ["".join(chars) for n in range(5) for chars in itertools.product("ab", repeat=n)]
    for text in strings:
        for pattern in strings:
            final = string_steps(text, pattern, algorithm)[-1]["state"]
            assert final["match_index"] == text.find(pattern)


def test_kmp_no_text_backtracking_and_less_comparisons_on_adversarial_text():
    text, pattern = "a" * 60 + "b", "a" * 12 + "b"
    kmp = string_steps(text, pattern)
    indices = [step["state"]["i"] for step in kmp]
    assert indices == sorted(indices)
    assert kmp[-1]["state"]["comparisons"] < string_steps(text, pattern, "bf")[-1]["state"]["comparisons"]
    assert string_steps("ababcabcacbab", "abcac")[-1]["state"]["match_index"] == 5


def test_queue_wraparound_full_empty_and_fifo():
    operations = [{"operation": "enqueue", "value": 1}, {"operation": "enqueue", "value": 2},
                  {"operation": "enqueue", "value": 99}, {"operation": "dequeue"},
                  {"operation": "enqueue", "value": 3}, {"operation": "dequeue"}, {"operation": "dequeue"}, {"operation": "dequeue"}]
    steps = queue_steps(3, operations)
    assert [step["state"]["result"] for step in steps if step["operation"] == "dequeue"] == [1, 2, 3]
    assert any(step["operation"] == "full" for step in steps)
    assert steps[-1]["state"]["empty"] and steps[-1]["state"]["size"] == 0
    for step in steps:
        state = step["state"]
        assert (state["rear"] - state["front"] + 3) % 3 == state["size"]


def test_stack_lifo():
    steps = stack_steps(2, [{"operation": "push", "value": 1}, {"operation": "push", "value": 2}, {"operation": "pop"}, {"operation": "pop"}])
    assert [step["state"]["result"] for step in steps if step["operation"] == "pop"] == [2, 1]


def test_invalid_algorithm_parameters_rejected():
    for payload in [{"algorithm": "other"}, {"algorithm": "queue", "capacity": -2}, {"algorithm": "kmp", "text": "a" * 121}, {"algorithm": "linked_list", "values": {}}]:
        with pytest.raises(ValidationError):
            generate_steps(payload)
