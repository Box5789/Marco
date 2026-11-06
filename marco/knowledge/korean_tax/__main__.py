"""One JSON object in, one JSON result out. No network, persistence or secrets."""
import json
import sys
from . import evaluate_scenario


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        print(json.dumps({'status':'invalid_input','reason':'유효한 JSON 객체가 필요합니다.'},ensure_ascii=False))
        return 2
    result = evaluate_scenario(data)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'computed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
