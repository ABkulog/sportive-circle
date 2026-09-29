Feature: Profiles
  People can see who they're playing with, and control what others see.

  @FR-PROF-1
  Scenario: New Huskies can add a photo later
    When someone signs up with the email "dubs@uw.edu"
    And they enter the code that was emailed to "dubs@uw.edu"
    And they tap "Add later"
    Then they can open the feed

  @FR-PROF-2
  Scenario: Hidden photo location data is removed
    Given "Maya" is a Husky
    When "Maya" uploads a photo that has GPS data in it
    Then the saved photo is a 640 by 640 JPEG without GPS data

  @FR-PROF-3
  Scenario: Your own profile has one Edit profile button, and Add photo only without a photo
    Given "Maya" is a Husky
    When "Maya" opens her own profile
    Then they see "Edit profile"
    And they don't see "Add photo"
    And they don't see "Change photo"

  @FR-PROF-4
  Scenario: Emails are private until you've played together
    Given "Maya" is a Husky
    And "Jordan" is a Husky
    When "Jordan" opens Maya's profile
    Then they don't see "maya@uw.edu"
    Given "Maya" hosts a basketball game tomorrow
    And "Jordan" joins Maya's game
    When "Jordan" opens Maya's profile
    Then they don't see "maya@uw.edu"
    Given "Maya" hosted a basketball game yesterday that "Jordan" played in
    When "Jordan" opens Maya's profile
    Then they see "maya@uw.edu"

  @FR-PROF-6
  Scenario: People can add their Instagram so others can DM them there
    Given "Maya" is a Husky
    And "Jordan" is a Husky
    When "Maya" adds her Instagram "maya.hoops" and the pronouns "she/her"
    And "Jordan" opens Maya's profile
    Then they see "@maya.hoops"
    And they see "she/her"

  @FR-BADGE-2
  Scenario: Admins give the Tester badge to the people who tested the app
    Given "Maya" is a Husky
    And "Admin" is an admin
    When "Admin" gives "Maya" the Tester badge
    And "Maya" opens her own profile
    Then they see "Tester"

  @FR-INFO-1
  Scenario: How it works is three short steps
    When a visitor opens How it works
    Then they see "Find a game"
    And they see "Start your own"
    And they see "Join a club"
    And they don't see "Words you'll see"
