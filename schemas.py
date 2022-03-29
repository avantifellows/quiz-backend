def userEntity(item) -> dict:
    return {
        "uuid": item["uuid"],
        "questions": item["questions"],
    }


def usersEntity(entity) -> list:
    return [userEntity(item) for item in entity]


def QuestionEntity(item) -> dict:
    return {
        "uuid": item["uuid"],
        "instructions": item["instructions"],
        "text": item["text"],
        "type": item["type"],
        "options": item["options"],
    }


def QuestionsEntity(entity) -> list:
    return [QuestionEntity(item) for item in entity]
