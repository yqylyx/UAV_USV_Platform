"""Offline design-artifact checks only; does not test business implementations."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
from jsonschema import Draft7Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
CHECKER = FormatChecker()

@CHECKER.checks("date-time", raises=ValueError)
def valid_utc_timestamp(value):
    # A strict UTC subset avoids depending on optional jsonschema format extras.
    if not isinstance(value, str):
        return True  # The schema's type constraint handles this.
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value):
        return False
    datetime.fromisoformat(value[:-1] + "+00:00")
    return True

def main():
    schema = json.loads((ROOT / 'contracts.schema.json').read_text(encoding='utf-8'))
    fixtures = json.loads((ROOT / 'fixtures.json').read_text(encoding='utf-8'))
    Draft7Validator.check_schema(schema)
    definitions = schema['definitions']
    def walk(value):
        if isinstance(value, dict):
            if '$ref' in value:
                target = value['$ref']
                assert target.startswith('#/definitions/'), f'External reference forbidden: {target}'
                assert target.split('/')[-1] in definitions, f'Missing definition: {target}'
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
    seen = set()
    failures = []
    for case in fixtures['cases']:
        assert case['id'] not in seen, 'Duplicate fixture ID'
        seen.add(case['id'])
        definition = case['definition']
        selected = {'$schema':schema['$schema'], '$ref':'#/definitions/'+definition,
                    'definitions':definitions}
        errors = list(Draft7Validator(selected, format_checker=CHECKER).iter_errors(case['data']))
        if (not errors) != case['valid']:
            failures.append((case['id'], [error.message for error in errors]))
    assert not failures, f'Fixture expectation failures: {failures}'
    golden = fixtures['goldenPlan']
    canonical = json.dumps(golden['data'],sort_keys=True,separators=(',',':'),ensure_ascii=True)
    assert canonical == golden['canonicalJson'], 'Golden canonical serialization differs'
    assert hashlib.sha256(canonical.encode('utf-8')).hexdigest() == golden['sha256'], 'Golden hash differs'
    for path in ROOT.glob('*.md'):
        text = path.read_text(encoding='utf-8')
        assert len(re.findall(r'^```', text, re.M)) % 2 == 0, f'Unbalanced fence: {path.name}'
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if ':' not in link and not link.startswith('#'):
                assert (path.parent / link.split('#')[0]).exists(), f'Broken link: {path.name}: {link}'
    tests = (ROOT / 'test-design.md').read_text(encoding='utf-8')
    business_ids = re.findall(r'^\| ([ARIPFC]\d{2}) \|', tests, re.M)
    assert len(business_ids) == 76, 'Missing business-test cases'
    assert len(business_ids) == len(set(business_ids)), 'Duplicate business-test ID'
    prepare_schema = json.loads((ROOT / 'prepare-response.schema.json').read_text(encoding='utf-8'))
    prepare_cases = json.loads((ROOT / 'prepare-response.fixtures.json').read_text(encoding='utf-8'))['cases']
    Draft7Validator.check_schema(prepare_schema)
    for case in prepare_cases:
        assert Draft7Validator(prepare_schema).is_valid(case['data']) == case['valid'], case['id']
    print(f'PASS: {len(prepare_cases)} prepare response fixtures')
    print(f'PASS: schema + {len(seen)} positive/negative fixtures + golden plan hash + local links/fences')
    print(f'Design inventory: {len(business_ids)} business cases; NOT EXECUTED (design only).')
    print('No application, database, provider, Unity or ROS connection was made.')

if __name__ == '__main__':
    main()