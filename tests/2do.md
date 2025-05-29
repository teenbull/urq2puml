2do
===

- [ ] подумать над возможностью пакетной обработки файлов (придется убрать sublime сообщения из puml_gen)
- [ ] юнит-тесты для парсера
- [ ] юнит-тесты для генератора
- [ ] собрать все предметы inv+ в одно подсостояние
- [ ] предметы - в другое
- [ ] проверять используются ли все предметы и все переменные в коде (для статистики)
- [ ] использовать подсостояния для локаций с одним префиксом
- [ ] подсостояния для системных локаций и локаций с одинаковыми префиксами (use_, inv_):


Примеры кода:

@startuml
scale 350 width
[*] --> NotShooting

state NotShooting {
  [*] --> Idle
  Idle --> Configuring : EvConfig
  Configuring --> Idle : EvConfig
}

state Configuring {
  [*] --> NewValueSelection
  NewValueSelection --> NewValuePreview : EvNewValue
  NewValuePreview --> NewValueSelection : EvNewValueRejected
  NewValuePreview --> NewValueSelection : EvNewValueSaved

  state NewValuePreview {
     State1 -> State2
  }

}
@enduml

Пример:

@startuml
skinparam stateArrowColor #606060
skinparam state {
    BackgroundColor #F0F8FF
    BorderColor #A9A9A9
    FontColor #303030
    ArrowFontColor #404040
}
skinparam state<<tech>> {
    BackgroundColor #7692AD
    FontColor #FFFFFF
}
skinparam state<<orphan>> {
    BackgroundColor #ffcccb
    FontColor #303030
}

sprite $menu_icon <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8.2 11.2">
  <path d="M0 0v11.2l3-2.9.1-.1h5.1L0 0z" fill="#3D3D3D"/>
</svg>
sprite $local_icon <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 12">
  <path d="M1.2 0 C0.4 0 0 0.4 0 1.2 L0 12 L4 9 L8 12 L8 1.2 C8 0.4 7.6 0 6.8 0 Z" fill="#CD5C5C" />
</svg>

state "1" as 0 <<tech>>
0: Нет описания

state "метка" as 1 #d0f0d0
1: Нет описания

state Use {
    state "use_предмет" as 2 <<tech>>
    2: sdfdsf
    
    state "use_предмет3" as 3 <<tech>>
    3: sdfs
    
    state "use_предмет2" as 4 <<tech>>
    4: 1
}

state Inv {
    state "inv_предмет" as 5 <<tech>>
    5: 21
    
    state "inv_предмет2" as 6 <<tech>>
    6: 1
}

[*] #828282 --> 0 
0 --> 1 : (текст)
0 --> Use
0 --> Inv

@enduml
