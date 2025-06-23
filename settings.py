# settings.py
# Определяет классы для хранения и управления настройками плагина.

class ColorOptions:
    """Хранит все настройки цветов."""
    def __init__(self, config_dict=None):
        cfg = config_dict or {}
        # Цвета для состояний
        self.end_color = cfg.get('end_color', '#d0f0d0')
        self.cycle_color = cfg.get('cycle_color', '#ffffcc')
        self.proc_target_color = cfg.get('proc_target_color', '#E6E6FA')
        self.tech_color = cfg.get('tech_color', '#B0E8FF')
        self.orphan_color = cfg.get('orphan_color', '#ffcccb')
        self.double_color = cfg.get('double_color', '#ffcccb')

class FormatOptions:
    """Хранит все строковые форматы для PlantUML."""
    def __init__(self, config_dict=None):
        cfg = config_dict or {}
        self.proc_full = cfg.get('proc_full', "{} --> {} : [proc]\\n{} -[dotted]-> {}\n")
        self.proc_simplified = cfg.get('proc_simplified', "{} -[bold,dotted]-> {} : [proc] ({})\n")

class Settings:
    """Главный контейнер, объединяющий все группы настроек."""
    def __init__(self, settings_object=None):
        # settings_object - это объект, возвращаемый sublime.load_settings
        cfg = settings_object or {}
        
        # Создаем экземпляры дочерних классов, передавая им соответствующую часть словаря настроек
        self.colors = ColorOptions(cfg.get('colors', {}))
        self.formats = FormatOptions(cfg.get('formats', {}))
        
        # Общие настройки, не вошедшие в группы
        self.puml_jar_path = cfg.get('puml_jar_path', "")
        self.proc_links = cfg.get('proc_links', True)