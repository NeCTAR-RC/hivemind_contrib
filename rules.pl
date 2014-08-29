% -*- mode: prolog -*-

sum_list([], 0).
sum_list([H | Rest], Sum) :- sum_list(Rest,Tmp), Sum is H + Tmp.

first_list([], _).
first_list([F], F).
first_list([F | Rest], F).

score(Category, Score, User) :-
  gerrit:commit_label(label(Category, Score), User).

add_category_min_score(In, Category, Min,  P) :-
  %% sum the review scores
  findall(Score, score(Category, Score, User), Scores),
  sum_list(Scores, Sum),

  %% sum the author scores
  gerrit:commit_author(Author),
  findall(AuthorScore, score(Category, AuthorScore, Author), AuthorScores),
  sum_list(AuthorScores, AuthorSum),

  %% calculate the total
  Sum - AuthorSum >= Min, !,

  findall(User, score(Category, Score, User), Users),
  first_list(Users, FirstUser),
  P = [label(Category, ok(FirstUser)) | In].

add_category_min_score(In, Category, Min, P) :-
  P = [label(Category, need(Min)) | In].

submit_rule(S) :-
  gerrit:default_submit(X),
  X =.. [submit | Ls],
  gerrit:commit_author(Author),
  gerrit:remove_label(Ls, ok(_), NoCR),
  gerrit:remove_label(NoCR, label('Code-Review', _), NoCR1),
  add_category_min_score(NoCRl, 'Code-Review', 2, Labels),
  S =.. [submit | Labels].
