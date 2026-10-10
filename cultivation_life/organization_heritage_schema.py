"""Pure storage validation, independent from enabled content and runtime."""
def validate(value):
    def require(condition):
        if not condition: raise ValueError('无效组织传承记录')
    require(isinstance(value,dict))
    if not value: return
    require(set(value)<= {'books','revision','history','research_year','line_successor','rename_available'})
    books=value.get('books')
    require(isinstance(books,list) and len(books)<=512)
    require(all(isinstance(k,str) and 0<len(k)<=160 for k in books))
    require(len(set(books))==len(books))
    require(type(value.get('revision')) is int and value['revision']>=0)
    rows=value.get('history')
    require(isinstance(rows,list) and len(rows)<=16)
    for row in rows:
        require(isinstance(row,dict) and type(row.get('year')) is int and row['year']>=0 and isinstance(row.get('text'),str))
    if 'research_year' in value: require(type(value['research_year']) is int and value['research_year']>=0)
    if 'line_successor' in value: require(isinstance(value['line_successor'],str) and bool(value['line_successor']))
    if 'rename_available' in value: require(type(value['rename_available']) is bool)
