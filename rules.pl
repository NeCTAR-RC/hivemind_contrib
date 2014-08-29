% -*- mode: prolog -*-

sum_list([], 0).
sum_list([H | Rest], Sum) :- sum_list(Rest,Tmp), Sum is H + Tmp.

score(Category, Score, User) :-
  gerrit:commit_label(label(Category, Score), User).

% Sum the votes in a category. Uses a helper function score/2
% to select out only the score values the given category.
sum(VotesNeeded, Category, label(Category, ok(_))) :-
  %% sum the review scores
  findall(Score, score(Category, Score, User), All),
  sum_list(All, Sum),

  %% sum the author scores
  gerrit:commit_author(Author),
  findall(AuthorScore, score(Category, AuthorScore, Author), AuthorScores),
  sum_list(AuthorScores, AuthorSum),

  %% calculate the total
  Sum - AuthorSum >= VotesNeeded, !,
  !.
sum(VotesNeeded, Category, label(Category, need(VotesNeeded))).

submit_rule(S) :-
  sum(2, 'Code-Review', CR),
  gerrit:max_with_block(-1, 1, 'Verified', V).
