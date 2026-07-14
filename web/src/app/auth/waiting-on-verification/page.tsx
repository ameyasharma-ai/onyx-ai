import { getCurrentUserSS } from "@/lib/users/svcSS";
import { getAuthTypeMetadataSS } from "@/lib/auth/svcSS";
import { AuthTypeMetadata } from "@/lib/auth/types";
import { redirect } from "next/navigation";
import { User } from "@/lib/types";
import { RequestNewVerificationEmail } from "./RequestNewVerificationEmail";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";

export default async function Page() {
  // catch cases where the backend is completely unreachable here
  // without try / catch, will just raise an exception and the page
  // will not render
  let authTypeMetadata: AuthTypeMetadata | null = null;
  let currentUser: User | null = null;
  try {
    [authTypeMetadata, currentUser] = await Promise.all([
      getAuthTypeMetadataSS(),
      getCurrentUserSS(),
    ]);
  } catch (e) {
    console.log(`Some fetch failed for the login page - ${e}`);
  }

  if (!currentUser) {
    return redirect("/auth/login");
  }

  if (!authTypeMetadata?.requiresVerification || currentUser.is_verified) {
    return redirect("/app");
  }

  return (
    <AuthFlowContainer>
      <div className="flex flex-col items-center justify-center p-8 gap-6 text-center text-gray-300">
        <div className="flex flex-col gap-2">
          <p>
            Hey <strong>{currentUser.email}</strong>, it looks like you haven't verified your email yet.
          </p>
          <p>Check your inbox for an email from us to get started!</p>
        </div>
        <div className="flex flex-col items-center gap-2 mt-4">
          <p className="text-sm text-gray-400">Didn't receive an email?</p>
          <RequestNewVerificationEmail email={currentUser.email}>
            <button className="w-full flex items-center justify-center gap-2 py-3 px-6 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl transition-all duration-200 shadow-md shadow-indigo-900/20">
              Resend Verification Email
            </button>
          </RequestNewVerificationEmail>
        </div>
      </div>
    </AuthFlowContainer>
  );
}
