Feature: Accept an invitation
  As an invitee
  I want to accept an invitation sent to my email address
  So that I become a member of the organisation

  Rule: The invitee must be logged in with the exact email address the
        invitation was sent to.  Accepting creates a members row,
        activates the invited org as the user's default org, and marks
        the invitation accepted.  Expired invitations are not accepted.

  Scenario Outline: Happy path accept
    Given a pending invitation "<token>" to "<invitee_email>" for "<org>" as "<role>" sent <sent_days_ago> days ago
    And user "<user>" is logged in as "<user_email>"
    When "<user>" accepts invitation "<token>"
    Then the invitation is marked "accepted"
    And "<user>" is a "<role>" of "<org>"
    And "<user>"'s default org is "<org>"
    And an InvitationAccepted event is emitted

    Examples:
      | token  | org       | invitee_email     | role   | user  | user_email      | sent_days_ago | now        | outcome |
      | tok-b  | Acme Corp | bob@example.com   | member | bob   | bob@example.com | 1             | 1700000000 | success |
      | tok-c  | Acme Corp | carol@example.com | admin  | carol | carol@example.com | 6           | 1700000000 | success |

  Scenario Outline: Accept with wrong email is rejected
    Given a pending invitation "<token>" to "<invitee_email>" for "<org>" as "<role>" sent <sent_days_ago> days ago
    And user "<user>" is logged in as "<user_email>"
    When "<user>" accepts invitation "<token>"
    Then the accept fails with code EMAIL_MISMATCH
    And the invitation is still "pending"
    And an AcceptFailed event is emitted

    Examples:
      | token  | org       | invitee_email     | role   | user  | user_email       | sent_days_ago | now        | outcome                  |
      | tok-d  | Acme Corp | bob@example.com   | member | alice | alice@example.com | 1            | 1700000000 | error:EmailMismatchError |

  Scenario Outline: Expired invitation cannot be accepted
    Given a pending invitation "<token>" to "<invitee_email>" for "<org>" as "<role>" sent <sent_days_ago> days ago
    And user "<user>" is logged in as "<user_email>"
    When "<user>" accepts invitation "<token>"
    Then the accept fails with code INVITATION_EXPIRED
    And the invitation is still "pending"
    And an AcceptFailed event is emitted

    Examples:
      | token  | org       | invitee_email   | role   | user  | user_email    | sent_days_ago | now        | outcome                      |
      | tok-e  | Acme Corp | old@example.com | member | old   | old@example.com | 8           | 1700000000 | error:InvitationExpiredError |
