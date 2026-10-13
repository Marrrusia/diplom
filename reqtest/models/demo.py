"""Ручной демонстрационный пример, не результат работы LLM."""
from reqtest.models.domain import Element, ElementType, Project, Requirement


def demo_project() -> Project:
    """Создать пример без выдуманного поведения при Instance != CRC."""
    requirement = Requirement(
        id="SDD_MVA_INIT_F_00040",
        text="При вызове подкомпонента HAL_CRC_MspInit компонент INIT должен выполнить следующее: если значение поля Instance структуры crcHandle равно константе CRC, необходимо включить тактирование модуля CRC вызовом макроса __HAL_RCC_CRC_CLK_ENABLE() без аргументов",
    )
    elements = [
        Element(id="E001", requirement_id=requirement.id, type=ElementType.CONDITION,
                description="Вызов HAL_CRC_MspInit", source_fragment="При вызове подкомпонента HAL_CRC_MspInit"),
        Element(id="E002", requirement_id=requirement.id, type=ElementType.CONDITION,
                description="crcHandle.Instance равно CRC", source_fragment="значение поля Instance структуры crcHandle равно константе CRC"),
        Element(id="E003", requirement_id=requirement.id, type=ElementType.ACTION,
                description="Включить тактирование CRC через указанный макрос", source_fragment="включить тактирование модуля CRC вызовом макроса __HAL_RCC_CRC_CLK_ENABLE()"),
        Element(id="E004", requirement_id=requirement.id, type=ElementType.CONSTRAINT,
                description="Макрос вызывается без аргументов", source_fragment="без аргументов"),
    ]
    return Project(name="Пример CRC", requirements=[requirement], elements=elements)
