import pytest
from unittest.mock import patch, MagicMock, AsyncMock
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

@pytest.mark.asyncio
async def test_generate_interview_question(mock_jd_text, mock_user_profile, mock_skills_gap):
    # Setup mock LLM response with an AI tell
    mock_result = MagicMock()
    mock_result.text = "As an AI, I suggest you ask: How would you delve into learning Django for this role?"
    mock_call_llm = AsyncMock(return_value=mock_result)

    # Execute
    with patch("backend.services.interview_simulator.call_llm", new=mock_call_llm):
        result = await generate_interview_question(mock_jd_text, mock_user_profile, mock_skills_gap)

    # Verify
    mock_call_llm.assert_called_once()
    assert "As an AI" not in result
    assert "delve" not in result
    assert "explore" in result or "ask: How would you" in result

@pytest.mark.asyncio
async def test_generate_interview_question_empty_inputs():
    result = await generate_interview_question("", "", "")
    assert "Can you tell me about your background?" in result

@pytest.mark.asyncio
async def test_evaluate_interview_answer(mock_jd_text):
    mock_result = MagicMock()
    mock_result.text = "As an AI, your answer is good but could be more robust."
    mock_call_llm = AsyncMock(return_value=mock_result)

    question = "How would you learn Django?"
    answer = "I would read the documentation."

    with patch("backend.services.interview_simulator.call_llm", new=mock_call_llm):
        result = await evaluate_interview_answer(question, answer, mock_jd_text)

    mock_call_llm.assert_called_once()
    assert "As an AI" not in result
    assert "robust" not in result
    assert "strong" in result or "your answer is good" in result

@pytest.mark.asyncio
async def test_evaluate_interview_answer_empty_inputs():
    result = await evaluate_interview_answer("", "", "")
    assert "Insufficient context" in result
