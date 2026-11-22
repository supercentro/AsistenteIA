## ADDED Requirements

### Requirement: The arrival of an answer does not take the focus from another control

After an answer arrives, the question box SHALL receive the focus only when the focus is on the question form or has fallen to the page body. A control the student moved to, such as the confirmation of a deletion or a conversation button, SHALL keep the focus.

#### Scenario: The focus returns to the box after a normal answer
- **WHEN** the student sends a question and the focus is on the form or the send button, which becomes disabled while the answer is pending
- **THEN** the box receives the focus when the answer arrives

#### Scenario: An open confirmation keeps the focus
- **WHEN** the student opens the delete confirmation of a conversation while an answer is pending and the answer arrives
- **THEN** the confirmation group keeps the focus, the answer is shown, and the confirm control stays disabled until the answer has arrived

#### Scenario: A conversation button keeps the focus
- **WHEN** the focus is on another control of the page when the answer arrives
- **THEN** that control keeps the focus
