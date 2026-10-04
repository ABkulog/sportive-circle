Feature: Accounts
  Only UW students can join, and they can always get back into their account.

  @FR-AUTH-1
  Scenario: A non-UW email can't sign up
    When someone signs up with the email "dubs@gmail.com"
    Then they see "Please use your UW email address"
    And no account exists for "dubs@gmail.com"

  @FR-AUTH-1 @FR-AUTH-2
  Scenario: A UW student signs up and confirms their email
    When someone signs up with the email "dubs@uw.edu"
    And they enter the code that was emailed to "dubs@uw.edu"
    Then they are logged in
    And they are asked to add a profile picture

  @FR-AUTH-2
  Scenario: A wrong code doesn't work
    When someone signs up with the email "dubs@uw.edu"
    And they enter the code "000000"
    Then they see "Wrong code, try again."

  @FR-AUTH-3
  Scenario: You must be at least 18
    When someone born 17 years ago signs up with the email "kid@uw.edu"
    Then they see "You need to be 18 or older"

  @FR-AUTH-4
  Scenario: Too many wrong passwords lock the account for a while
    Given "Maya" is a Husky
    When "Maya" logs in with the wrong password 10 times
    And "Maya" logs in with the right password
    Then they see "Try again in 15 minutes"

  @FR-AUTH-5
  Scenario: Forgot password
    Given "Maya" is a Husky
    When "Maya" asks to reset her password
    And "Maya" enters the reset code and the new password "brand-new-pass"
    Then they are logged in
    And "Maya" can log in with the password "brand-new-pass"

  @FR-AUTH-5
  Scenario: The reset page doesn't reveal who has an account
    When someone asks to reset the password for "nobody@uw.edu"
    Then they see "If that email has an account, we sent it a 6-digit code"

  @FR-AUTH-6
  Scenario: Change password from settings
    Given "Maya" is a Husky
    When "Maya" changes her password to "even-better-pass"
    Then they see "Password changed."
    And "Maya" can log in with the password "even-better-pass"

  @FR-AUTH-7
  Scenario: Deleting an account needs the word DELETE and the password
    Given "Maya" is a Husky
    When "Maya" tries to delete her account without typing DELETE
    Then they see "Your account was not deleted"
    When "Maya" deletes her account properly
    Then no account exists for "maya@uw.edu"

  @FR-AUTH-8 @FR-SAFE-2
  Scenario: A suspended account can't log in
    Given "Maya" is a Husky
    And "Admin" is an admin
    When "Admin" suspends "Maya"
    And "Maya" logs in with the right password
    Then they see "This account is suspended"
