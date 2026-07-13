import pytest
from unittest.mock import patch, MagicMock
from backend.services.interview_simulator import generate_interview_question, evaluate_interview_answer

@pytest.fixture
def mock_jd_text():
    return "Looking for a Python developer with Django and Redis experience."

@pytest.fixture
def mock_user_profile():
    return "Python developer with Flask experience."

@pytest.fixture
def mock_skills_gap():
    return "Missing Django and Redis experience."

@patch("backend.services.interview_simulator.anthropic.Anthropic")
def test_generate_interview_question(mock_anthropic, mock_jd_text, mock_user_profile, mock_skills_gap):
    # Setup mock LLM response
    mock_client = MagicMock()
    mock_message = MagicMock()
    # Provide a response with an AI tell
    mock_message.content = [MagicMock(text="As an AI, I suggest you ask: How would you delve into learning Django for this role?")]
    mock_client.messages.create.return_value = mock_message
    mock_anthropic.return_value = mock_client

    # Execute
    result = generate_interview_question(mock_jd_text, mock_user_profile, mock_skills_gap)

    # Verify
    mock_client.messages.create.assert_called_once()
    assert "As an AI" not in result
    assert "delve" not in result
    assert "explore" in result or "ask: How would you" in result

def test_generate_interview_question_empty_inputs():
    result = generate_interview_question("", "", "")
    assert "Can you tell me about your background?" in result

@patch("backend.services.interview_simulator.anthropic.Anthropic")
def test_evaluate_interview_answer(mock_anthropic, mock_jd_text):
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="As an AI, your answer is good but could be more robust.")]
    mock_client.messages.create.return_value = mock_message
    mock_anthropic.return_value = mock_client

    question = "How would you learn Django?"
    answer = "I would read the documentation."

    result = evaluate_interview_answer(question, answer, mock_jd_text)

    mock_client.messages.create.assert_called_once()
    assert "As an AI" not in result
    assert "robust" not in result
    assert "strong" in result or "your answer is good" in result

def test_evaluate_interview_answer_empty_inputs():
    result = evaluate_interview_answer("", "", "")
    assert "Insufficient context" in result
