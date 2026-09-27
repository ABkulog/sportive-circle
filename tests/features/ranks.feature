Feature: Ranks
  Ranks keep harder games fun without locking anyone out forever.

  Background:
    Given "Maya" is a Husky
    And "Jordan" is a Husky

  @FR-RANK-1 @FR-RANK-2
  Scenario: Everyone starts at Casual, so Competitive games are locked at first
    When "Maya" tries to host a Competitive basketball game
    Then they see "For players who've reached Competitive"

  @FR-RANK-3
  Scenario: Props after a game
    Given "Maya" hosted a basketball game yesterday that "Jordan" played in
    When "Jordan" gives Maya props
    Then they see "Props sent!"

  @FR-RANK-3
  Scenario: You can't give yourself props
    Given "Maya" hosted a basketball game yesterday that "Jordan" played in
    When "Maya" gives herself props
    Then they see "you can't give yourself props"
