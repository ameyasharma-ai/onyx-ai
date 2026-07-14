import Link from "next/link";
import Image from "next/image";

export default function AuthFlowContainer({
  children,
  authState,
  footerContent,
}: {
  children: React.ReactNode;
  authState?: "signup" | "login" | "join";
  footerContent?: React.ReactNode;
}) {
  return (
    <div className="relative p-4 flex flex-col items-center justify-center min-h-screen bg-[#09090b] overflow-hidden text-white">
      {/* Premium Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-600/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-violet-600/20 blur-[120px] pointer-events-none" />
      
      <div className="relative z-10 w-full max-w-[420px] flex items-center flex-col bg-[#18181b]/60 backdrop-blur-2xl rounded-3xl border border-white/10 shadow-2xl p-10 transform transition-all hover:scale-[1.01] duration-500">
        <div className="flex flex-col items-center justify-center mb-8 w-full gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-inner overflow-hidden shadow-black/50">
            <span className="text-xl font-bold text-white tracking-tight">P</span>
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight text-white mb-2">PersonaLabs</h1>
            <p className="text-sm text-gray-400 font-medium">Conversations that remember.</p>
          </div>
        </div>
        <div className="w-full">{children}</div>
      </div>
      
      <div className="relative z-10 mt-8">
        {authState === "login" && (
          <div className="text-sm text-center w-full text-gray-400 mx-auto">
            {footerContent ?? (
              <>
                New to PersonaLabs?{" "}
                <Link
                  href="/auth/signup"
                  className="text-white hover:text-indigo-300 font-medium transition-colors duration-200"
                >
                  Create an account
                </Link>
              </>
            )}
          </div>
        )}
        {authState === "signup" && (
          <div className="text-sm text-center w-full text-gray-400 mx-auto">
            Already have an account?{" "}
            <Link
              href="/auth/login?autoRedirectToSignup=false"
              className="text-white hover:text-indigo-300 font-medium transition-colors duration-200"
            >
              Sign In
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
