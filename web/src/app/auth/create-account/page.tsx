"use client";

import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import { REGISTRATION_URL } from "@/lib/constants";
import { Button } from "@opal/components";
import Link from "next/link";
import { SvgImport } from "@opal/icons";

export default function Page() {
  return (
    <AuthFlowContainer>
      <div className="flex flex-col space-y-6">
        <h2 className="text-2xl font-bold text-text-900 text-center">
          Account Not Found
        </h2>
        <p className="text-gray-300 max-w-md text-center">
          We couldn&apos;t find your account in our records. To access PersonaLabs, you
          need to either:
        </p>
        <ul className="list-disc text-left text-gray-400 w-full pl-6 mx-auto">
          <li>Be invited to an existing PersonaLabs team</li>
          <li>Create a new PersonaLabs team</li>
        </ul>
        <div className="flex justify-center">
          <Link
            href={`${REGISTRATION_URL}/register`}
            className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl transition-all duration-200 shadow-md shadow-indigo-900/20"
          >
            Create New Organization
          </Link>
        </div>
        <p className="text-sm text-text-500 text-center">
          Have an account with a different email?{" "}
          <Link
            href="/auth/login"
            className="text-action-link-05 hover:underline"
          >
            Sign in
          </Link>
        </p>
      </div>
    </AuthFlowContainer>
  );
}
