from app.models.workshop import PlotRequest, Shot, Character, StoryboardResult, CharactersResult

def test_plot_request():
    r = PlotRequest(story="少女与黑猫")
    assert r.story == "少女与黑猫"

def test_storyboard_result_parses_list():
    s = StoryboardResult.model_validate({
        "shots": [
            {"shot":"远景","description":"雨夜涩谷","duration":"3s","movement":"缓慢推进","dialogue":""},
            {"shot":"特写","description":"黑猫眼睛","duration":"1s","movement":"推近","dialogue":"救救我"},
        ]
    })
    assert len(s.shots) == 2
    assert s.shots[0].shot == "远景"
    assert s.shots[1].dialogue == "救救我"

def test_characters_result_parses_list():
    c = CharactersResult.model_validate({
        "characters": [{"name":"林月","role":"主角","description":"17岁少女"}]
    })
    assert c.characters[0].name == "林月"
