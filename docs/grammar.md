┌──────────────────────────────────────────────────────────────────────┐
│                    FINAL SMART COMPILER GRAMMAR                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ Program                                                              │
│   → DeclarationList                                                  │
│                                                                      │
│ DeclarationList                                                      │
│   → Declaration DeclarationList                                      │
│   | ε                                                                │
│                                                                      │
│ Declaration                                                          │
│   → Type ID ;                                                        │
│   | Type ID = Expr ;                                                 │
│   | Function                                                         │
│                                                                      │
│ Type                                                                 │
│   → int                                                              │
│   | float                                                            │
│                                                                      │
│ Function                                                             │
│   → Type ID ( ParamList ) Block                                      │
│                                                                      │
│ ParamList                                                            │
│   → Param ParamList'                                                 │
│   | ε                                                                │
│                                                                      │
│ ParamList'                                                           │
│   → , Param ParamList'                                                │
│   | ε                                                                │
│                                                                      │
│ Param                                                                │
│   → Type ID                                                          │
│                                                                      │
│ Stmt                                                                 │
│   → Declaration                                                      │
│   | Assignment                                                       │
│   | IfStmt                                                           │
│   | WhileStmt                                                        │
│   | ReturnStmt                                                       │
│   | PrintStmt                                                        │
│   | ExprStmt                                                         │
│   | Block                                                            │
│                                                                      │
│ Assignment                                                           │
│   → ID = Expr ;                                                      │
│                                                                      │
│ IfStmt                                                               │
│   → if ( Expr ) Stmt                                                 │
│   | if ( Expr ) Stmt else Stmt                                       │
│                                                                      │
│ WhileStmt                                                            │
│   → while ( Expr ) Stmt                                              │
│                                                                      │
│ Block                                                                │
│   → { StmtList }                                                     │
│                                                                      │
│ StmtList                                                             │
│   → Stmt StmtList                                                    │
│   | ε                                                                │
│                                                                      │
│ ReturnStmt                                                           │
│   → return ;                                                         │
│   | return Expr ;                                                    │
│                                                                      │
│ PrintStmt                                                            │
│   → printf ( Expr ) ;                                                │
│                                                                      │
│ Expr                                                                 │
│   → RelExpr                                                           │
│                                                                      │
│ RelExpr                                                              │
│   → AddExpr RelOp AddExpr                                            │
│   | AddExpr                                                           │
│                                                                      │
│ RelOp                                                                │
│   → < | > | <= | >= | == | !=                                        │
│                                                                      │
│ AddExpr                                                              │
│   → MulExpr AddExpr'                                                 │
│                                                                      │
│ AddExpr'                                                             │
│   → + MulExpr AddExpr'                                               │
│   | - MulExpr AddExpr'                                               │
│   | ε                                                                │
│                                                                      │
│ MulExpr                                                              │
│   → UnaryExpr MulExpr'                                               │
│                                                                      │
│ MulExpr'                                                             │
│   → * UnaryExpr MulExpr'                                             │
│   | / UnaryExpr MulExpr'                                             │
│   | % UnaryExpr MulExpr'                                             │
│   | ε                                                                │
│                                                                      │
│ UnaryExpr                                                            │
│   → + UnaryExpr                                                      │
│   | - UnaryExpr                                                      │
│   | Primary                                                          │
│                                                                      │
│ Primary                                                              │
│   → ID                                                               │
│   | INT_LITERAL                                                      │
│   | FLOAT_LITERAL                                                    │
│   | FunctionCall                                                     │
│   | ( Expr )                                                         │
│                                                                      │
│ FunctionCall                                                         │
│   → ID ( ArgList )                                                   │
│                                                                      │
│ ArgList                                                              │
│   → Expr ArgList'                                                    │
│   | ε                                                                │
│                                                                      │
│ ArgList'                                                             │
│   → , Expr ArgList'                                                  │
│   | ε                                                                │
│                                                                      │
│ ExprStmt                                                             │
│   → Expr ;                                                           │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘