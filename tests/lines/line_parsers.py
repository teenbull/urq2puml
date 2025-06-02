# line_parsers.py
import re

LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
COMMENTS_REMOVAL = re.compile(r'/\*.*?\*/|;[^\n]*', re.MULTILINE | re.DOTALL)

class TestLoc:
    def __init__(self, id_val, name, line):
        self.id = id_val
        self.name = name
        self.line = line

    def __eq__(self, other):
        if not isinstance(other, TestLoc):
            return NotImplemented
        return self.id == other.id and self.name == other.name and self.line == other.line

    def __repr__(self):
        return f"TestLoc(id='{self.id}', name='{self.name}', line={self.line})"

def prep_content_silent(content):
    content = COMMENTS_REMOVAL.sub('', content)        
    content = re.sub(r'\n\s*_', '', content)
    content = re.sub(r'"', '\'', content)
    lines = []
    for line_text in content.split('\n'):
        if re.match(r'^\s*if\b', line_text, re.IGNORECASE):
            parts = re.split(r'\b(then|else)\b', line_text, flags=re.IGNORECASE)
            lines.extend(p.lstrip() for p in parts if p.lstrip() and p.lstrip().lower() not in ('then', 'else'))
        else:
            lines.append(line_text)
    return '\n'.join(p.strip() for p in '\n'.join(lines).split('&') if p.strip())

def parse_locations_only_lines1_silent(orig_content):
    clean_content = prep_content_silent(orig_content)
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
    locs = []
    if len(orig_matches) != len(clean_matches):
        pass

    for i, clean_m in enumerate(clean_matches): 
        name_from_clean = clean_m.group(1).strip() 
        real_line = -1
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            pos_colon_in_match = orig_m.group(0).find(':')
            if pos_colon_in_match != -1:
                abs_pos_colon = orig_m.start() + pos_colon_in_match
                num_prev_nl = orig_content[:abs_pos_colon].count('\n')
                real_line = num_prev_nl + 1
            else: 
                num_prev_nl = orig_content[:orig_m.start()].count('\n')
                real_line = num_prev_nl + 1
                if orig_m.start() > 0 and orig_content[orig_m.start()] == '\n':
                     potential_line_content = orig_content[orig_m.start():].split('\n', 1)[0]
                     if potential_line_content.strip().startswith(':'):
                        real_line +=1
        else: 
            num_prev_nl_clean = clean_content[:clean_m.start()].count('\n')
            real_line = num_prev_nl_clean + 1
            if clean_m.start() > 0 and clean_content[clean_m.start()] == '\n':
                 potential_line_content_clean = clean_content[clean_m.start():].split('\n', 1)[0]
                 if potential_line_content_clean.strip().startswith(':'):
                    real_line +=1
        locs.append(TestLoc(str(i), name_from_clean, real_line))
    return locs

def parse_locations_only_lines2_silent(orig_content):
    clean_content = prep_content_silent(orig_content)
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
    locs = []
    if len(orig_matches) != len(clean_matches):
        pass

    cumulative_newlines_in_orig = 0
    last_colon_pos_in_orig = 0 

    for i, clean_m in enumerate(clean_matches): 
        name_from_clean = clean_m.group(1).strip() 
        real_line = -1
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            pos_colon_in_match_group = orig_m.group(0).find(':')
            if pos_colon_in_match_group != -1:
                abs_pos_colon_current = orig_m.start() + pos_colon_in_match_group
                if last_colon_pos_in_orig > abs_pos_colon_current : 
                    cumulative_newlines_in_orig = orig_content[:abs_pos_colon_current].count('\n')
                else:
                    newlines_in_segment = orig_content.count('\n', last_colon_pos_in_orig, abs_pos_colon_current)
                    cumulative_newlines_in_orig += newlines_in_segment
                real_line = cumulative_newlines_in_orig + 1
                last_colon_pos_in_orig = abs_pos_colon_current
            else: 
                num_prev_nl = orig_content[:orig_m.start()].count('\n')
                real_line = num_prev_nl + 1
                if orig_m.start() > 0 and orig_content[orig_m.start()] == '\n':
                     potential_line_content = orig_content[orig_m.start():].split('\n', 1)[0]
                     if potential_line_content.strip().startswith(':'):
                        real_line +=1
                last_colon_pos_in_orig = orig_m.start() 
        else: 
            num_prev_nl_clean = clean_content[:clean_m.start()].count('\n')
            real_line = num_prev_nl_clean + 1
            if clean_m.start() > 0 and clean_content[clean_m.start()] == '\n' :
                 potential_line_content_clean = clean_content[clean_m.start():].split('\n', 1)[0]
                 if potential_line_content_clean.strip().startswith(':'):
                    real_line +=1
        locs.append(TestLoc(str(i), name_from_clean, real_line))
    return locs

def parse_locations_only_lines3_silent(orig_content):
    """Версия с точным маппингом позиций между оригиналом и очищенным контентом"""
    clean_content = prep_content_silent(orig_content)
    
    # Находим все локации в обоих версиях
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
    
    locs = []
    
    # Строим детальную карту соответствий между оригиналом и очищенным контентом
    orig_lines = orig_content.split('\n')
    clean_lines = clean_content.split('\n')
    
    # Находим все строки с локациями в оригинале
    orig_loc_lines = {}  # line_num -> (match_obj, abs_pos_of_colon)
    for m in orig_matches:
        colon_pos = m.start() + m.group(0).find(':')
        line_num = orig_content[:colon_pos].count('\n') + 1
        orig_loc_lines[line_num] = (m, colon_pos)
    
    # Для каждой локации в очищенном контенте найти соответствующую в оригинале
    for i, clean_m in enumerate(clean_matches):
        name_from_clean = clean_m.group(1).strip()
        
        # Попробуем найти точное соответствие по имени локации
        real_line = -1
        
        # Ищем в оригинале локацию с таким же именем в правильном порядке
        matched_orig_line = None
        used_lines = set()
        
        for orig_line_num, (orig_match, _) in sorted(orig_loc_lines.items()):
            if orig_line_num in used_lines:
                continue
            orig_name = orig_match.group(1).strip()
            if orig_name == name_from_clean:
                matched_orig_line = orig_line_num
                used_lines.add(orig_line_num)
                break
        
        if matched_orig_line:
            real_line = matched_orig_line
        elif i < len(orig_matches):
            # Фоллбэк на позиционное соответствие
            orig_m = orig_matches[i]
            colon_pos = orig_m.start() + orig_m.group(0).find(':')
            real_line = orig_content[:colon_pos].count('\n') + 1
        else:
            # Последний фоллбэк
            real_line = clean_content[:clean_m.start()].count('\n') + 1
        
        locs.append(TestLoc(str(i), name_from_clean, real_line))
    
    return locs