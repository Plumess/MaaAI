"""Task truth comes from source IDs, never OCR predictions."""
def target(row,characters):
    """将来源角色 ID 等信息映射到 MAA 任务实际比较的文字。"""
    if row['id'].startswith('rules/') and row.get('task_name')=='CharsNameOcrReplace':
        pointer=row['source']['json_pointer'];parts=pointer.split('/')
        if len(parts)!=3 or parts[2]!='name':raise ValueError('unexpected character source pointer')
        key=parts[1].replace('~1','/').replace('~0','~')
        return characters[key]['name'], '/chars/'+parts[1]+'/name'
    return row['label'],None
