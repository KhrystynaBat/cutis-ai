CLASS_CODES: tuple[str, ...] = ("akiec", "bcc", "bkl", "df", "mel", "nv", "vasc")

CLASS_LABELS_UK: dict[str, str] = {
    "akiec": "Актинічний кератоз / внутрішньоепідермальна карцинома",
    "bcc": "Базальноклітинна карцинома",
    "bkl": "Доброякісний кератоз",
    "df": "Дерматофіброма",
    "mel": "Меланома",
    "nv": "Меланоцитарний невус",
    "vasc": "Судинне ураження",
}

CLASS_INDEX: dict[str, int] = {code: i for i, code in enumerate(CLASS_CODES)}

INPUT_SIZE = 128
NUM_CLASSES = len(CLASS_CODES)

MODEL_NAME = "ensemble_best"
MODEL_FILE = "ensemble_best.h5"
MODEL_SHA256 = "4890489c3ea6a5a8aeaeab934be1f44c3fc841d34b735c4f75a99c608aad3af9"

XAI_COMPONENTS: tuple[tuple[str, str, int], ...] = (
    ("AlexNet", "activation_5", 8),
    ("ResNet", "activation_29", 5),
    ("DenseNet", "activation_91", 4),
)
