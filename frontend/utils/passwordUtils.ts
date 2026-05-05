export type StrengthLevel = "weak" | "fair" | "strong" | "very_strong";

export interface PasswordStrength {
  level: StrengthLevel;
  score: 1 | 2 | 3 | 4;
}

export function checkPasswordStrength(password: string): PasswordStrength {
  if (password.length < 8) return { level: "weak", score: 1 };

  const checks = [
    /[A-Z]/.test(password),   // uppercase
    /[a-z]/.test(password),   // lowercase
    /[0-9]/.test(password),   // number
    /[^A-Za-z0-9]/.test(password), // special character
  ];
  const passed = checks.filter(Boolean).length;

  if (passed === 4) return { level: "very_strong", score: 4 };
  if (passed === 3) return { level: "strong",      score: 3 };
  return              { level: "fair",         score: 2 };
}
