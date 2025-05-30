# PlantUML Formatter - формирует содержимое PlantUML диаграмм

# ----------------------------------------------------------------------
# Лимиты
LOC_LIMIT = 40
DESC_LIMIT = 50
BTN_LIMIT = 30

# Цвета
PHANTOM_COLOR = "#ffcccb"
ORPHAN_COLOR = "#ffcccb"  # красный фон для сироток
PHANTOM_ARROW_COLOR = "#CD5C5C"

STATE_BG_COLOR = "#F0F8FF"
BORDER_COLOR = "#A9A9A9"
FONT_COLOR = "#303030"
ARROW_COLOR = "#606060"
ARROW_FONT_COLOR = "#404040"

CYCLE_COLOR = "#ffffcc"
DOUBLE_COLOR = "#ffcccb"
END_COLOR = "#d0f0d0"

# BLUE_COLOR = "#6fb4d4"


BTN_MENU_COLOR = "dotted" # для кнопок-меню
BTN_LOCAL_COLOR = "#cccccc,bold" # для локальных кнопок
DOT_COLOR = "#5A6B7D" # серый для стартовой точки
# Цвета для технических локаций
# TECH_COLOR = "#6fb4d4"  # светло-серый фон
# TECH_FONT_COLOR = "#FFFFFF"  # белый текст

TECH_COLOR = "#B0E8FF"  # светло-серый фон
# TECH_FONT_COLOR = "#FFFFFF"  # белый текст

GROUP_TITLE_COLOR = "#6F8194"  # темнее для заголовка
GROUP_FONT_COLOR = "#FFFFFF"

# PlantUML элементы
PHANTOM_NODE = f"""state "//phantom" as PHANTOM_NODE_URQ {PHANTOM_COLOR} {{
  PHANTOM_NODE_URQ: (Ссылка на несуществующую локацию)
}}
"""
SKIN_PARAMS = f"""skinparam stateArrowColor {ARROW_COLOR}
skinparam state {{
    BackgroundColor {STATE_BG_COLOR}
    BorderColor {BORDER_COLOR}
    FontColor {FONT_COLOR}
    ArrowFontColor {ARROW_FONT_COLOR}
}}
skinparam state<<tech>> {{
    BackgroundColor {TECH_COLOR}
}}
skinparam state<<orphan>> {{
    BackgroundColor {ORPHAN_COLOR}
    FontColor {FONT_COLOR}
}}
skinparam state<<group>> {{
    BackgroundColor {GROUP_TITLE_COLOR}
    FontColor {GROUP_FONT_COLOR}
}}
sprite $menu_icon <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8.2 11.2">
  <path d="M0 0v11.2l3-2.9.1-.1h5.1L0 0z" fill="#3D3D3D"/>
</svg>
sprite $local_icon <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 12">
  <path d="M1.2 0 C0.4 0 0 0.4 0 1.2 L0 12 L4 9 L8 12 L8 1.2 C8 0.4 7.6 0 6.8 0 Z" fill="#CD5C5C" />
</svg>
"""

START_LOC = f"[*] {DOT_COLOR} --> {{}} \n"  # Template for start location

# Форматы связей
AUTO_FMT = "{} -[dotted]-> {}\n"
BTN_FMT = "{} --> {} : ({})\n" 
PHANTOM_FMT = f"{{}} -[{PHANTOM_ARROW_COLOR},dashed]-> PHANTOM_NODE_URQ : ({{}})\n"
BTN_MENU = f"{{}} -[{BTN_MENU_COLOR}]-> {{}} : ({{}}) <$menu_icon> \n"
BTN_LOCAL = f"{{}} -[{BTN_LOCAL_COLOR}]-> {{}} : ({{}}) <$local_icon> \n"
DOUBLE_FMT = '{}: [Дубликат метки, строка {}]\\n\\n{}\n'
GOTO_FMT = "{} --> {} : [goto]\n"
PROC_FMT = "{} --> {} : [proc]\n{} -[dotted]-> {}\n"

STATE_FMT = 'state "{}" as {}'
STATE_CYCLE_FMT = f'state "{{}}" as {{}} {CYCLE_COLOR}' # For cycle states
STATE_END_FMT = f'state "{{}}" as {{}} {END_COLOR}'   # For end states
STATE_DESC_FMT = '{}: {}\n'
# ----------------------------------------------------------------------

class PumlFormatter:
    """Форматтер PlantUML диаграмм"""
    def __init__(self):
        self.warnings = []

    def _is_valid_loc(self, loc):
        """Проверяет валидность объекта локации"""
        return hasattr(loc, 'id') and hasattr(loc, 'name')

    def format_puml(self, locs):
        """Формирует содержимое PUML файла"""
        has_phantom = any(link[4] for loc in locs for link in loc.links if len(link) > 4)
        content_parts = []
        
        # Группируем локации
        ungrouped, groups = self._group_by_prefix(locs)
        
        # Рендерим все группы и локации
        content_parts.extend(self._render_groups(groups, ungrouped, locs=locs))

        # Дубликаты
        for loc in locs:
            if loc.dup:
                clean_name = self._limit_text(loc.name, LOC_LIMIT)
                clean_desc = self._limit_text(loc.desc, DESC_LIMIT)
                
                state_line = f'state "{clean_name}" as {loc.id} {DOUBLE_COLOR}'
                content_parts.extend([state_line + "\n", DOUBLE_FMT.format(loc.id, loc.line, clean_desc)])

        # Связи
        content_parts.append(self._add_all_links(locs))
        
        # Финальная сборка
        final_parts = ["@startuml\n"]
        if has_phantom:
            final_parts.append(PHANTOM_NODE)
        final_parts.append(SKIN_PARAMS)
        final_parts.extend(content_parts)
        final_parts.append("@enduml\n")
        
        return ''.join(final_parts)

    def _group_by_prefix(self, locs):
        """Группирует локации по префиксам рекурсивно (до _ или пробела)"""
        def build_tree(locs_list, depth=0):
            if depth > 3 or len(locs_list) < 2:
                return locs_list, {}
            
            groups, ungrouped = {}, []
            
            for loc in locs_list:
                name_parts = loc.name.lower().replace(' ', '_').split('_')
                if len(name_parts) > depth:
                    prefix = name_parts[depth] if depth < len(name_parts) else name_parts[-1]
                    groups.setdefault(prefix, []).append(loc)
                else:
                    ungrouped.append(loc)
            
            # Рекурсивно группируем подгруппы
            final_groups = {}
            for prefix, group_locs in groups.items():
                if len(group_locs) >= 2:
                    sub_ungrouped, sub_groups = build_tree(group_locs, depth + 1)
                    final_groups[prefix] = (sub_ungrouped, sub_groups)
                else:
                    ungrouped.extend(group_locs)
            
            return ungrouped, final_groups
        
        return build_tree(locs)

    def _render_location(self, loc, indent=""):
        """Рендерит одну локацию"""
        clean_name = self._limit_text(loc.name, LOC_LIMIT)
        clean_desc = self._limit_text(getattr(loc, 'desc', ''), DESC_LIMIT)
        
        # Определяем стереотип и формат одним проходом
        if hasattr(loc, 'tech') and loc.tech:
            state_line = f'{indent}{STATE_FMT.format(clean_name, loc.id)} <<tech>>'
        elif hasattr(loc, 'orphan') and loc.orphan:
            state_line = f'{indent}{STATE_FMT.format(clean_name, loc.id)} <<orphan>>'
        elif hasattr(loc, 'cycle') and loc.cycle:
            state_line = f'{indent}{STATE_CYCLE_FMT.format(clean_name, loc.id)}'
        elif hasattr(loc, 'end') and loc.end:
            state_line = f'{indent}{STATE_END_FMT.format(clean_name, loc.id)}'
        else:
            state_line = f'{indent}{STATE_FMT.format(clean_name, loc.id)}'
            
        return [state_line + "\n", f"{indent}{STATE_DESC_FMT.format(loc.id, clean_desc)}"]

    def _render_groups(self, groups, ungrouped, indent="", locs=None):
        """Рендерит группы рекурсивно"""
        parts = []
        
        # Валидные локации (включая дубликаты)
        valid_ungrouped = [loc for loc in ungrouped if self._is_valid_loc(loc)]
        valid_ungrouped.sort(key=lambda x: int(x.id) if x.id.isdigit() else float('inf'))
        
        # Добавляем [*] если есть локация 0 в этой группе
        if locs and any(loc.id == '0' for loc in valid_ungrouped):
            parts.append(f"{indent}{START_LOC.format('0')}")
        
        for loc in valid_ungrouped:
            parts.extend(self._render_location(loc, indent))
        
        # Группы
        for prefix, (sub_ungrouped, sub_groups) in sorted(groups.items()):
            parts.extend([
                f"{indent}state {prefix.capitalize()} <<group>> {{\n",
                *self._render_groups(sub_groups, sub_ungrouped, indent + "    ", locs),
                f"{indent}}}\n"
            ])
        
        return parts

    def _add_all_links(self, locs):
        """Добавляет все связи (группировка не влияет на связи)"""
        parts = []
        
        for loc in locs:
            for link in loc.links:
                target_id, target_name, link_type, label, is_phantom, is_menu, is_local = link
                
                if is_phantom:
                    parts.append(self._format_phantom_link(loc.id, target_name, link_type, label))
                    self._add_warning(f"Локация '{target_name}' для {link_type} из '{loc.name}' не найдена")
                else:
                    parts.append(self._format_link(loc.id, target_id, link_type, label, is_menu, is_local))
        
        return ''.join(parts)

    def _format_link(self, source_id, target_id, link_type, label, is_menu=False, is_local=False):
        """Форматирует обычные связи, включая спец. цвета для меню и локальных кнопок"""
        if link_type == "auto":            
            return AUTO_FMT.format(source_id, target_id)
        elif link_type == "btn":
            clean_label = self._limit_text(label, BTN_LIMIT)
            if is_menu:
                return BTN_MENU.format(source_id, target_id, clean_label)
            elif is_local:
                return BTN_LOCAL.format(source_id, target_id, clean_label)
            else:
                return BTN_FMT.format(source_id, target_id, clean_label)
        elif link_type == "goto":
            return GOTO_FMT.format(source_id, target_id)
        elif link_type == "proc":
            return PROC_FMT.format(source_id, target_id, target_id, source_id)
        
        return ""

    def _format_phantom_link(self, source_id, target_name, link_type, label):
        """Форматирует phantom связь"""
        label = self._limit_text(label if link_type == "btn" and label else target_name, BTN_LIMIT)
        return PHANTOM_FMT.format(source_id, label)

    def _limit_text(self, text, max_len):
        """Ограничивает длину текста для диаграммы"""
        if not text or len(text) <= max_len:
            return text or ""
        return text[:max_len].strip() + "..."

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"PlantUML Formatter Warning: {message}")

    def get_warnings(self):
        """Возвращает предупреждения"""
        return self.warnings