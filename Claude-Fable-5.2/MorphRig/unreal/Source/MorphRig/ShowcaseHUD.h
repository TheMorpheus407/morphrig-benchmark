#pragma once
#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "ShowcaseHUD.generated.h"

class AOperativeCharacter;

/** Canvas overlay: state / clip / time / speed / marker data, skeleton overlay, status labels, subtitles. Appears in frame captures. */
UCLASS()
class MORPHRIG_API AShowcaseHUD : public AHUD
{
	GENERATED_BODY()
public:
	virtual void DrawHUD() override;

private:
	void Line(const FString& Text, const FLinearColor& Color = FLinearColor::White, float Scale = 1.f);
	void DrawSkeleton(AOperativeCharacter* Ch);
	void DrawClipBar(const struct FOpClipPlay& Play, const TCHAR* Label, const FLinearColor& Color);
	float CursorX = 0.f, CursorY = 0.f;
	float FrameMsSmoothed = 16.6f;
};
