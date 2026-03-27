"""
Thin rule-engine adapter for eval use.
Evaluates YAML-defined tax rules against a set of taxpayer facts.

This is intentionally minimal: it only needs to support the benchmark
case format in src/benchmarks/ and the rule format in src/rules/.
When a real rule engine exists in the application layer, this adapter
can be replaced.
"""
import yaml

from eval.config import REPO_ROOT


def load_rules(rules_files: list[str]) -> list[dict]:
    """Load and concatenate rules from one or more YAML files."""
    all_rules = []
    for rf in rules_files:
        path = REPO_ROOT / rf
        if not path.exists():
            raise FileNotFoundError(f"Rules file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        if isinstance(rules, list):
            all_rules.extend(rules)
    return all_rules


def _eval_condition(condition: dict, state: dict) -> bool:
    """Evaluate a single condition against the current state."""
    node = condition["node"]
    operator = condition["operator"]
    expected = condition["value"]

    if node not in state:
        return False

    actual = state[node]

    if expected == "any":
        return True

    if operator == "eq":
        if isinstance(expected, list):
            return actual in expected
        return actual == expected

    if operator == "in":
        if isinstance(expected, list):
            return actual in expected
        return actual == expected

    if operator == "not_in":
        if isinstance(expected, list):
            return actual not in expected
        return actual != expected

    if operator == "contains":
        if isinstance(actual, list):
            return expected in actual
        return actual == expected

    if operator == "lt":
        return actual < expected

    if operator == "gt":
        return actual > expected

    if operator == "gte":
        return actual >= expected

    if operator == "lte":
        return actual <= expected

    raise ValueError(f"Unknown operator: {operator}")


def _check_conditions(rule: dict, state: dict) -> bool:
    """Check whether a rule's conditions are met."""
    if "conditions" in rule:
        if not all(_eval_condition(c, state) for c in rule["conditions"]):
            return False

    if "conditions_any" in rule:
        if not any(_eval_condition(c, state) for c in rule["conditions_any"]):
            return False

    if "conditions" not in rule and "conditions_any" not in rule:
        return True

    return True


def _apply_action(rule: dict, state: dict):
    """Apply a rule's action to the state."""
    action = rule["actions"]
    target = rule["target"]
    action_type = action["type"]
    value = action["value"]

    if action_type == "set":
        state[target] = value
    elif action_type == "append":
        if target not in state:
            state[target] = []
        if isinstance(state[target], list):
            if value not in state[target]:  # idempotent: no duplicates
                state[target].append(value)
        else:
            if state[target] != value:
                state[target] = [state[target], value]
    else:
        raise ValueError(f"Unknown action type: {action_type}")


def run_rule_case(facts: dict, rules_files: list[str]) -> dict:
    """
    Run a set of rules against the given facts and return the final state.

    Args:
        facts: dict of taxpayer facts (input nodes)
        rules_files: list of rule YAML file paths relative to repo root

    Returns:
        dict of all state (input facts + derived/decision values)
    """
    rules = load_rules(rules_files)
    state = dict(facts)

    for _pass in range(5):
        changed = False
        for rule in rules:
            if _check_conditions(rule, state):
                target = rule["target"]
                old_value = state.get(target)
                _apply_action(rule, state)
                if state.get(target) != old_value:
                    changed = True
        if not changed:
            break

    return state
