# Book Quiz — Frontend Component Tree

```
<App>
├── <Layout>
│   ├── <Header>
│   │   ├── <Logo />
│   │   ├── <SearchBar />            # Always visible, minimal
│   │   └── <AuthButtons>            # Login / Sign Up / User Menu
│   │       ├── <LoginButton />
│   │       ├── <SignUpButton />
│   │       └── <UserMenu>           # When authenticated
│   └── <Outlet />                   # react-router page content
│
├── Routes
│   ├── "/" → <LandingPage>
│   │   ├── <HeroSection>
│   │   │   ├── <Heading />
│   │   │   ├── <SubHeading />
│   │   │   └── <SearchBar />        # Primary search (large)
│   │   ├── <FeaturedBooks />        # Optional: popular books
│   │   └── <HowItWorks />
│   │
│   ├── "/search?q=..." → <SearchResultsPage>
│   │   ├── <SearchBar />            # Refine search
│   │   ├── <SearchResultList>
│   │   │   └── <BookCard />*        # One per result
│   │   │       ├── <BookCover />
│   │   │       ├── <BookInfo />
│   │   │       └── <StartQuizButton />
│   │   └── <Pagination />
│   │
│   ├── "/books/:id" → <BookDetailPage>
│   │   ├── <BookHeader>
│   │   │   ├── <BookCover />
│   │   │   └── <BookMeta />
│   │   ├── <BookDescription />
│   │   ├── <StartQuizButton />
│   │   └── <UserProgress />         # If authenticated
│   │
│   ├── "/quiz/:attemptId" → <QuizPage>
│   │   ├── <QuizProgress>
│   │   │   ├── <ProgressBar />
│   │   │   └── <QuestionCounter />  # "Question 3 of 10"
│   │   ├── <QuestionCard>
│   │   │   ├── <QuestionText />
│   │   │   ├── <ChoiceList>
│   │   │   │   └── <ChoiceButton />* # One per choice
│   │   │   └── <FeedbackOverlay />   # Correct/incorrect flash
│   │   └── <QuizNavigation>
│   │       ├── <NextButton />
│   │       └── <SubmitButton />     # On last question
│   │
│   ├── "/quiz/:attemptId/complete" → <QuizCompletePage>
│   │   ├── <ScoreDisplay>
│   │   │   ├── <ScoreCircle />      # Animated score
│   │   │   └── <ScoreMessage />
│   │   ├── <ResultBreakdown>
│   │   │   └── <ResultItem />*      # Per-question result
│   │   ├── <GuestEmailCapture />    # If not logged in
│   │   ├── <RetakeButton />
│   │   └── <BackToBooksButton />
│   │
│   ├── "/login" → <LoginPage>
│   │   └── <AuthForm mode="login" />
│   │
│   ├── "/signup" → <SignUpPage>
│   │   └── <AuthForm mode="signup" />
│   │
│   └── "/profile" → <ProfilePage>  # Requires auth
│       ├── <ProfileHeader>
│       │   ├── <Avatar />
│       │   └── <UserStats />
│       └── <BookProgressList>
│           └── <BookProgressCard />*
│               ├── <BookCover />
│               ├── <BookInfo />
│               ├── <AttemptHistory />
│               └── <ContinueButton />
```

## State Management

| State Category       | Tool              | Example                          |
|----------------------|-------------------|----------------------------------|
| Server state         | React Query       | Book list, quiz data, profile    |
| Auth state           | Zustand + cookies | JWT token, user info             |
| UI state             | useState / Zustand| Quiz progress, selected choices  |
| Form state           | React Hook Form   | Login, signup, email capture     |
| URL state            | react-router      | Search query, current page       |
