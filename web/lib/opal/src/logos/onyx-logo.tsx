import type { IconProps } from "@opal/types";
const SvgOnyxLogo = ({ size, ...props }: IconProps) => (
  // eslint-disable-next-line @next/next/no-img-element
  <img
    src="/new_logo_1.svg"
    alt="Logo"
    width={size}
    height={size}
    style={{ objectFit: "contain" }}
    {...(props as React.ImgHTMLAttributes<HTMLImageElement>)}
  />
);
export default SvgOnyxLogo;
