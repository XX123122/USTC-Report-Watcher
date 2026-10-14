import json
from urllib.parse import urlsplit
from .security import load_secret


def shapes(value, prefix="", depth=0):
    if depth > 8:
        return []
    found = []
    if isinstance(value, list):
        found.append({"path": prefix, "count": len(value), "fields": list(value[0]) if value and isinstance(value[0], dict) else []})
        if value:
            found.extend(shapes(value[0], prefix + ".0", depth+1))
    elif isinstance(value, dict):
        for key, child in value.items():
            found.extend(shapes(child, (prefix + "." + key).lstrip("."), depth+1))
    return found


def discover(config):
    path = config.root / ".auth/discovery.bin"
    if not path.exists():
        raise RuntimeError("尚无调查数据。请运行 login，进入报告列表、翻页、打开详情并保存。")
    captures = load_secret(path)
    captures = [item for item in captures if '/sys/xsbgglappustc/modules/' in item['url']]
    summary = []
    for index, item in enumerate(captures):
        parts = urlsplit(item["url"])
        try:
            parameters = json.loads(item["body"] or "{}")
            parameter_names = list(parameters) if isinstance(parameters, dict) else []
        except ValueError:
            from urllib.parse import parse_qs
            parameter_names = list(parse_qs(item["body"] or ""))
        summary.append({"capture_index": index, "method": item["method"], "path": parts.path,
                        "parameter_names": parameter_names, "response_fields": list(item["json"]) if isinstance(item["json"], dict) else [],
                        "arrays": shapes(item["json"])})
    # Values, queries, authentication headers, and private report content are excluded.
    destination = config.root / "docs/discovery-schema.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def configure_verified_source(config, captures=None):
    """Recognize only the actually observed USTC list + detail pair and field metadata."""
    from urllib.parse import parse_qs
    from .parser import at_path
    from .auth import StructureError
    captures = captures if captures is not None else load_secret(config.root / '.auth/discovery.bin')
    lists = [item for item in captures if urlsplit(item['url']).path.endswith('/xsbgxk/wxbgbgdz.do') and at_path(item['json'], 'datas.wxbgbgdz.rows')]
    details = [item for item in captures if urlsplit(item['url']).path.endswith('/xsbgfb/xsbgfbbddz.do') and at_path(item['json'], 'datas.xsbgfbbddz.rows')]
    if not lists or not details:
        raise StructureError('会话已保存；还需在登录窗口打开报告列表并打开一条详情，才能自动确认数据源。')
    entry, detail = lists[0], details[0]
    row = at_path(entry['json'], 'datas.wxbgbgdz.rows.0')
    detail_row = at_path(detail['json'], 'datas.xsbgfbbddz.rows.0')
    if not {'BGBM','BGTMZW','DD','BGSJ'}.issubset(row) or not {'BGBM','BGNR','DD','BGSJ'}.issubset(detail_row):
        raise StructureError('实际报告字段结构不同，请检查 discover 导出的脱敏结构。')
    parameters = {k: value[0] for k, value in parse_qs(entry.get('body') or '', keep_blank_values=True).items()}
    detail_parameters = {k: value[0] for k, value in parse_qs(detail.get('body') or '', keep_blank_values=True).items()}
    if not {'pageSize','pageNumber'}.issubset(parameters) or 'BGBM' not in detail_parameters:
        raise StructureError('未捕获到可信分页和详情参数。')
    # Page size 100 was verified on the live API on 2026-10-14.
    parameters.update(pageSize=100, pageNumber=1)
    detail_parameters['BGBM'] = ''
    from datetime import datetime
    from zoneinfo import ZoneInfo
    source = {'verified': True, 'verified_at': datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(), 'api': {
        'url': entry['url'], 'method': entry['method'], 'encoding': 'form', 'parameters': parameters,
        'success_path': 'code', 'success_value': '0', 'rows_path': 'datas.wxbgbgdz.rows',
        'pagination': {'page_parameter': 'pageNumber', 'first_page': 1, 'total_path': 'datas.wxbgbgdz.totalSize'},
        'fields': {'report_id': 'BGBM', 'title_zh': 'BGTMZW', 'title_en': 'BGTMYW', 'speaker': 'BGRZW',
                   'department': 'YXDM_DISPLAY', 'location_raw': 'DD', 'location_full': 'DD', 'description': 'BZ', 'start_at': 'BGSJ',
                   'selectable_flag': 'SFKXK', 'registration_deadline': 'JZSJ'},
        'detail': {'url': detail['url'], 'method': detail['method'], 'encoding': 'form', 'parameters': detail_parameters,
                   'success_path': 'code', 'success_value': '0', 'id_parameter': 'BGBM', 'row_id_path': 'BGBM', 'id_path': 'BGBM',
                   'object_path': 'datas.xsbgfbbddz.rows.0', 'strategy': 'upcoming_or_unknown',
                   'fields': {'location_full': 'DD', 'description': ['BGNR', 'BZ'], 'start_at': 'BGSJ', 'speaker': 'BGRZW'}}}}
    # Match the observed JSON code's actual type, which varies across EMAP applications.
    source['api']['success_value'] = entry['json']['code']
    source['api']['detail']['success_value'] = detail['json']['code']
    destination = config.root / config['fetch']['source_file']
    from .security import secure_directory
    secure_directory(destination.parent)
    if destination.suffix == '.bin':
        from .security import save_secret
        save_secret(destination, source)
    else:
        destination.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination
