import { SvgUser } from "@opal/icons";
import { DEFAULT_AVATAR_SIZE_PX } from "@/lib/constants";
import { getUserEmail, getUserInitials } from "@/lib/users/svc";
import Text from "@/refresh-components/texts/Text";
import type { User } from "@/lib/types";

export interface UserAvatarProps {
  user: User | null;
  size?: number;
}

export default function UserAvatar({
  user,
  size = DEFAULT_AVATAR_SIZE_PX,
}: UserAvatarProps) {
  const userEmail = getUserEmail(user);
  const userInitials = getUserInitials(
    user?.personalization?.name ?? null,
    userEmail
  );

  if (user?.profile_photo_id) {
    return (
      <div
        className="flex items-center justify-center rounded-full overflow-hidden bg-background-tint-01"
        style={{ width: size, height: size }}
      >
        <img
          src={`/api/chat/file/${user.profile_photo_id}`}
          alt={`${userEmail} avatar`}
          className="w-full h-full object-cover"
        />
      </div>
    );
  }

  if (!userInitials) {
    return (
      <div
        role="img"
        aria-label={`${userEmail} avatar`}
        className="flex items-center justify-center rounded-full bg-background-tint-01"
        style={{ width: size, height: size }}
      >
        <SvgUser size={size * 0.55} className="stroke-text-03" aria-hidden />
      </div>
    );
  }

  return (
    <div
      role="img"
      aria-label={`${userEmail} avatar`}
      className="flex items-center justify-center rounded-full bg-background-neutral-inverted-00"
      style={{ width: size, height: size }}
    >
      <Text
        inverted
        secondaryAction
        text05
        className="select-none"
        style={{ fontSize: size * 0.4 }}
      >
        {userInitials}
      </Text>
    </div>
  );
}
