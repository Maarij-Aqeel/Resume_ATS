from app.utils.skill_ontology import normalize_skill, normalize_skills


def test_common_aliases():
    assert normalize_skill("reactjs") == "React"
    assert normalize_skill("React.js") == "React"
    assert normalize_skill("node") == "Node.js"
    assert normalize_skill("postgres") == "PostgreSQL"
    assert normalize_skill("k8s") == "Kubernetes"
    assert normalize_skill("js") == "JavaScript"


def test_dedupe():
    skills = ["React", "reactjs", "REACT", "node.js", "nodejs"]
    out = normalize_skills(skills)
    assert "React" in out
    assert "Node.js" in out
    assert len(out) == 2


def test_unknown_skill_titlecased():
    assert normalize_skill("SomeObscureTool") == "Someobscuretool"  # capwords behavior
