"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Text } from "@opal/components";
import { Spacer } from "@opal/components";
import { RequestNewVerificationEmail } from "../waiting-on-verification/RequestNewVerificationEmail";
import { User } from "@/lib/types";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";

export interface VerifyProps {
  user: User | null;
}

export default function Verify({ user }: VerifyProps) {
  const searchParams = useSearchParams();

  const [error, setError] = useState("");

  const verify = useCallback(async () => {
    const token = searchParams?.get("token");
    const firstUser =
      searchParams?.get("first_user") === "true" && NEXT_PUBLIC_CLOUD_ENABLED;
    if (!token) {
      setError(
        "Missing verification token. Try requesting a new verification email."
      );
      return;
    }

    const response = await fetch("/api/auth/verify", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token }),
    });

    if (response.ok) {
      // Redirect to login page instead of /app so user can log in
      // from any browser (not dependent on the original signup session)
      const loginUrl = firstUser
        ? "/auth/login?verified=true&first_user=true"
        : "/auth/login?verified=true";
      window.location.href = loginUrl;
    } else {
      let errorDetail = "unknown error";
      try {
        errorDetail = (await response.json()).detail;
      } catch (e) {
        console.error("Failed to parse verification error response:", e);
      }
      setError(
        `Failed to verify your email - ${errorDetail}. Please try requesting a new verification email.`
      );
    }
  }, [searchParams]);

  useEffect(() => {
    verify();
  }, [verify]);

  return (
    <AuthFlowContainer>
      <div className="flex flex-col items-center justify-center p-8">
        {!error ? (
          <>
            <Spacer rem={0.5} />
            <p className="text-gray-300">Verifying your email...</p>
          </>
        ) : (
          <div className="text-center">
            <Spacer rem={0.5} />
            <p className="text-red-400">{error}</p>

            {user && (
              <div className="mt-4">
                <RequestNewVerificationEmail email={user.email}>
                  <p className="text-sm mt-2 text-indigo-400 hover:text-indigo-300 cursor-pointer transition-colors duration-200">
                    Get new verification email
                  </p>
                </RequestNewVerificationEmail>
              </div>
            )}
          </div>
        )}
      </div>
    </AuthFlowContainer>
  );
}
