from .models import normalize, upcoming


def matches(report, config, now=None):
    rules = config["subscriptions"]
    if now and not upcoming(report, now):
        return False
    text = normalize(" ".join([report.title_zh, report.speaker, report.department,
                              report.location_full, report.description])).casefold()
    if any(normalize(word).casefold() in text for word in rules["exclude_keywords"]):
        return False
    modalities = set(rules["include_modalities"])
    if config["notification"]["notify_possible_online"]:
        modalities.add("possible_online")
    if report.modality not in modalities:
        return False
    if report.report_id in rules["watch_report_ids"]:
        return True
    title = report.title_zh.casefold()
    if rules["title_keywords_any"] and not any(normalize(w).casefold() in title for w in rules["title_keywords_any"]):
        return False
    if not all(normalize(w).casefold() in title for w in rules["title_keywords_all"]):
        return False
    for field, key in ((report.department, "department_keywords"), (report.speaker, "speaker_keywords")):
        if rules[key] and not any(normalize(w).casefold() in field.casefold() for w in rules[key]):
            return False
    return True
