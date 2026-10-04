Feature: Notifications
  People hear about what matters to them, where they want it, without being spammed.

  Background:
    Given "Maya" is a Husky
    And "Jordan" is a Husky
    And "Maya" and "Jordan" are friends

  @FR-NOTIF-1
  Scenario: A new message shows on the Messages icon only, not again in the bell
    When "Jordan" messages "Maya" "game tonight?"
    Then "Maya" has 1 on the Messages icon
    And "Maya" has 0 on the Bell icon
    When "Maya" opens her messages from "Jordan"
    Then "Maya" has 0 on the Messages icon

  @FR-NOTIF-2
  Scenario: Switching off direct messages
    When "Maya" switches off "messages" notifications
    And "Jordan" messages "Maya" "you up?"
    Then "Maya" has 0 on the Messages icon

  @FR-NOTIF-2
  Scenario: Switching everything off means no numbers and an empty bell
    When "Maya" switches off every notification
    And "Jordan" messages "Maya" "hello"
    Then "Maya" has 0 on the Messages icon
    And "Maya" has 0 on the Bell icon
    And "Maya" has nothing in the bell

  @FR-NOTIF-1
  Scenario: A host changing a game three times is one notice, not three
    Given "Maya" hosts a basketball game tomorrow
    And "Jordan" joins Maya's game
    When "Maya" changes the note of her game to "Bring water"
    And "Maya" changes the note of her game to "Bring a ball"
    And "Maya" changes the note of her game to "Court 3"
    Then "Jordan" has 1 on the Bell icon

  @FR-NOTIF-1
  Scenario: Club updates show on the Profile tab until you read them
    Given "Riley" is a Husky
    And "Riley" runs the approved club "UW Spikeball Club"
    And "Maya" follows "UW Spikeball Club"
    When "Riley" posts the club update "Practice moved to the Quad"
    Then "Maya" has 1 on the Profile tab
    When "Maya" opens Club updates
    Then "Maya" has 0 on the Profile tab

  @FR-NOTIF-1
  Scenario: Officers see people waiting to join on the Profile tab
    Given "Riley" is a Husky
    And "Riley" runs the approved club "UW Spikeball Club"
    When "Jordan" asks to join "UW Spikeball Club"
    Then "Riley" has 1 on the Profile tab

  @FR-NOTIF-3
  Scenario: New Need players posts show in the bell
    When "Jordan" posts that she needs 2 more for soccer in 15 minutes
    Then "Maya" has 0 on the Home tab
    And "Maya" sees "1 new Need players post" in the bell

  @FR-NOTIF-3
  Scenario: A brand-new account starts with nothing to catch up on
    Given "Riley" is a Husky
    And "Riley" runs the approved club "UW Spikeball Club"
    And "Riley" posts the club update "Welcome, everyone!"
    And "Sam" is a Husky
    When "Sam" follows "UW Spikeball Club"
    Then "Sam" has 0 on the Profile tab
