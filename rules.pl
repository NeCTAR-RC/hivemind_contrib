% -*- mode: prolog -*-

sum_list([], 0).
sum_list([H | Rest], Sum) :- sum_list(Rest,Tmp), Sum is H + Tmp.

first_list([], _).
first_list([F], F).
first_list([F | Rest], F).

score(Category, Score, User) :-
  gerrit:commit_label(label(Category, Score), User).

% Sum the votes in a category. Uses a helper function score/2
% to select out only the score values the given category.
sum(VotesNeeded, Category, P) :-
  %% sum the review scores
  findall(Score, score(Category, Score, User), All),
  sum_list(All, Sum),

  %% sum the author scores
  gerrit:commit_author(Author),
  findall(AuthorScore, score(Category, AuthorScore, Author), AuthorScores),
  sum_list(AuthorScores, AuthorSum),
  !,

  %% calculate the total
  Sum - AuthorSum >= VotesNeeded, !,
  findall(User, score(Category, Score, User), Users),
  first_list(Users, FirstUser),
  P = label(Category, ok(FirstUser)).
sum(VotesNeeded, Category, label(Category, need(VotesNeeded))).

submit_rule(S) :-
  sum(10, 'Code-Review', CR),
  gerrit:max_with_block(-1, 1, 'Verified', V).
