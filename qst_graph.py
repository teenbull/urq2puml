import re
import os
import subprocess
from pathlib import Path

def parse_urq_file(file_path):
    """Парсит URQ файл и возвращает структуру локаций и переходов"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Разбиваем файл на локации
    locations = {}
    transitions = []
    
    # Находим все локации (метки)
    location_blocks = re.split(r':([^\n]+)', content)[1:]  # Пропускаем первый элемент (текст до первой метки)
    
    for i in range(0, len(location_blocks), 2):
        if i+1 < len(location_blocks):
            location_name = location_blocks[i].strip()
            location_content = location_blocks[i+1].strip()
            
            # Извлекаем первое предложение из первого pln
            pln_match = re.search(r'pln\s+([^.\n]+)', location_content)
            description = pln_match.group(1).strip() if pln_match else "Нет описания"
            
            # Обрезаем длинные описания
            if len(description) > 40:
                description = description[:37] + "..."
            
            locations[location_name] = description
            
            # Находим все btn в этой локации
            btn_matches = re.finditer(r'btn\s+([^,\n]+),\s*([^\n]+)', location_content)
            for match in btn_matches:
                target_location = match.group(1).strip()
                button_text = match.group(2).strip()
                transitions.append((location_name, target_location, button_text))
    
    return locations, transitions

def generate_plantuml(locations, transitions, output_file):
    """Генерирует PlantUML код на основе локаций и переходов"""
    plantuml_code = "@startuml\n"
    
    # Добавляем настройки для красивого отображения
    plantuml_code += "skinparam state {\n"
    plantuml_code += "  BackgroundColor LightBlue\n"
    plantuml_code += "  BorderColor Blue\n"
    plantuml_code += "  FontName Arial\n"
    plantuml_code += "}\n\n"
    
    # Определяем состояния (локации)
    for name, description in locations.items():
        # Экранируем кавычки в описании
        description = description.replace('"', '\\"')
        plantuml_code += f'state "{name}\\n{description}" as {name.replace(" ", "_")}\n'
    
    plantuml_code += "\n"
    
    # Определяем переходы
    for source, target, label in transitions:
        # Экранируем кавычки в тексте кнопки
        label = label.replace('"', '\\"')
        if label and len(label) > 20:
            label = label[:17] + "..."
        
        # Проверяем, существует ли целевая локация
        if target in locations:
            plantuml_code += f'{source.replace(" ", "_")} --> {target.replace(" ", "_")} : "{label}"\n'
    
    plantuml_code += "@enduml"
    
    # Записываем PlantUML код в файл
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(plantuml_code)
    
    return plantuml_code

def generate_diagram(plantuml_file, output_image=None):
    """Генерирует изображение на основе PlantUML кода"""
    try:
        # Если выходной файл не указан, используем то же имя, что и у PlantUML файла
        if output_image is None:
            output_image = os.path.splitext(plantuml_file)[0] + ".png"
        
        # Используем PlantUML JAR для генерации изображения
        # Замените путь к JAR-файлу на свой
        cmd = ["java", "-jar", "plantuml.jar", plantuml_file]
        subprocess.run(cmd, check=True)
        
        print(f"Диаграмма сохранена в {output_image}")
        return True
    except Exception as e:
        print(f"Ошибка при генерации диаграммы: {e}")
        return False

def convert_urq_to_plantuml(urq_file):
    """Конвертирует URQ файл в PlantUML и генерирует изображение"""
    file_path = Path(urq_file)
    base_name = file_path.stem
    
    # Парсим URQ файл
    locations, transitions = parse_urq_file(urq_file)
    
    # Генерируем PlantUML код
    plantuml_file = file_path.with_suffix('.puml')
    plantuml_code = generate_plantuml(locations, transitions, plantuml_file)
    
    # Генерируем изображение
    generate_diagram(plantuml_file)
    
    return plantuml_file

# Пример использования
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        urq_file = sys.argv[1]
        convert_urq_to_plantuml(urq_file)
    else:
        print("Использование: python urq_to_plantuml.py путь_к_файлу.qst")