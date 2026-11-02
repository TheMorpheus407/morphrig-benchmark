// MorphRig - HUD, game mode and the searchable animation browser overlay.
#include "MorphRigHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "MorphRigCharacter.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigPerfLogger.h"

AMorphRigPerfLogger* AMorphRigHUD::FindPerfLogger() const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}
	TActorIterator<AMorphRigPerfLogger> It(World);
	if (It)
	{
		return *It;
	}
	return nullptr;
}

// ---------------------------------------------------------------------------
// game mode
// ---------------------------------------------------------------------------

AMorphRigGameMode::AMorphRigGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	HUDClass = AMorphRigHUD::StaticClass();
	DefaultPawnClass = AMorphRigCharacter::StaticClass();
	bStartPlayersAsSpectators = false;
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------

namespace
{
struct FHelpLine
{
	const TCHAR* Key;
	const TCHAR* Action;
};

static const FHelpLine GHelpLines[] = {
	{TEXT("W A S D"), TEXT("move (character relative)")},
	{TEXT("Mouse"), TEXT("look / aim")},
	{TEXT("Space"), TEXT("jump")},
	{TEXT("LMB"), TEXT("melee attack")},
	{TEXT("RMB"), TEXT("ranged shot")},
	{TEXT("Q"), TEXT("cast")},
	{TEXT("E"), TEXT("deploy prop")},
	{TEXT("Shift"), TEXT("dash (root motion, 2 m)")},
	{TEXT("Tab"), TEXT("cycle camera: close / side / front / top / face")},
	{TEXT("T"), TEXT("switch team accent")},
	{TEXT("L"), TEXT("cycle LOD 0 / 1 / 2")},
	{TEXT("K"), TEXT("skeleton overlay")},
	{TEXT("M"), TEXT("shading: textured / normal / clay")},
	{TEXT("N"), TEXT("toggle 1 / 10 instances")},
	{TEXT("[ ]"), TEXT("playback rate 0.5x - 1.5x")},
	{TEXT("R"), TEXT("reset character")},
	{TEXT("P"), TEXT("play the spoken performance")},
	{TEXT("Enter"), TEXT("run the deterministic showcase sequence")},
	{TEXT("F"), TEXT("open the animation browser")},
};
}

void AMorphRigHUD::DrawHUD()
{
	const double Start = FPlatformTime::Seconds();

	Super::DrawHUD();

	if (!Canvas || !GetOwningPlayerController())
	{
		FMorphRigFrameBreakdown::Current().Hud =
			(FPlatformTime::Seconds() - Start) * 1000.0;
		return;
	}

	UFont* Font = GEngine->GetMediumFont();
	const float Scale = 1.0f;
	const float X = 24.0f;
	float Y = 34.0f;

	AMorphRigCharacter* Character =
		Cast<AMorphRigCharacter>(GetOwningPlayerController()->GetPawn());

	// header
	DrawText(TEXT("MORPHRIG  //  OPERATIVE SEVEN"), FLinearColor(1.0f, 0.55f, 0.12f),
			 X, Y, Font, Scale);
	Y += 26.0f;

	if (Character)
	{
		const UMorphRigAnimInstance* AI = Character->GetMorphAnimInstance();
		const FString State = AI ? StaticEnum<EMorphRigState>()->GetNameStringByValue(
			static_cast<int64>(AI->State)) : TEXT("-");
		const FString Clip = AI ? AI->ActiveClip : TEXT("-");
		const float Time = AI ? AI->GetBaseTime() : 0.0f;

		DrawText(FString::Printf(TEXT("state   %s"), *State),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("clip    %s"), *Clip),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("time    %.2f s"), Time),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("speed   %.0f cm/s"), AI ? AI->MoveSpeed : 0.0f),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("rate    %.2f x"),
								 Character ? Character->GetPlayRate() : 1.0f),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("aim     yaw %.0f  pitch %.0f"),
								 AI ? AI->AimYaw : 0.0f, AI ? AI->AimPitch : 0.0f),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("lod     %d"), Character->GetLODIndex()),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("view    %s"), *Character->GetMaterialViewName()),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("team    %d"), Character->GetTeamIndex()),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("inst    %d"), Character->GetInstanceCount()),
				 FLinearColor::White, X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("event   %s"), AI ? *AI->LastEvent : TEXT("-")),
				 FLinearColor(0.4f, 0.9f, 1.0f), X, Y, Font, Scale); Y += 26.0f;
	}

	// frame time, straight from the logger actor
	if (AMorphRigPerfLogger* Perf = FindPerfLogger())
	{
		DrawText(FString::Printf(TEXT("fps     %.1f  (%.2f ms)"),
								 Perf->GetAverageFps(), Perf->GetAverageFrameMs()),
				 FLinearColor(0.55f, 1.0f, 0.65f), X, Y, Font, Scale); Y += 18.0f;
		DrawText(FString::Printf(TEXT("p99     %.2f ms"), Perf->GetWorstP99Ms()),
				 FLinearColor(0.55f, 1.0f, 0.65f), X, Y, Font, Scale); Y += 26.0f;
	}

	// controls
	DrawText(TEXT("CONTROLS"), FLinearColor(1.0f, 0.55f, 0.12f), X, Y, Font, Scale);
	Y += 20.0f;
	for (const FHelpLine& Line : GHelpLines)
	{
		DrawText(FString::Printf(TEXT("%-10s %s"), Line.Key, Line.Action),
				 FLinearColor(0.75f, 0.78f, 0.82f), X, Y, Font, Scale);
		Y += 15.0f;
	}

	// animation browser
	if (bBrowserVisible)
	{
		const float BW = 460.0f;
		const float BH = 520.0f;
		const float BX = Canvas->SizeX - BW - 24.0f;
		const float BY = 24.0f;
		DrawRect(FLinearColor(0.02f, 0.03f, 0.05f, 0.88f), BX, BY, BW, BH);
		DrawText(TEXT("ANIMATION BROWSER"), FLinearColor(1.0f, 0.55f, 0.12f),
				 BX + 14.0f, BY + 24.0f, Font, Scale);
		DrawText(FString::Printf(TEXT("filter: '%s'"), *BrowserFilter),
				 FLinearColor(0.7f, 0.75f, 0.8f), BX + 14.0f, BY + 44.0f, Font, Scale);

		const TArray<FString> Results = AMorphRigCharacter::SearchClips(BrowserFilter);
		float BY2 = BY + 66.0f;
		const int32 MaxRows = 28;
		const int32 Selection = Character ? Character->GetBrowserSelection() : 0;
		for (int32 i = 0; i < Results.Num() && i < MaxRows; ++i)
		{
			const bool bSelected = (i == Selection);
			DrawText((bSelected ? TEXT("> ") : TEXT("  ")) + Results[i],
					 bSelected ? FLinearColor(1.0f, 0.55f, 0.12f) : FLinearColor::White,
					 BX + 22.0f, BY2, Font, Scale);
			BY2 += 15.0f;
		}
		if (Results.Num() > MaxRows)
		{
			DrawText(FString::Printf(TEXT("... %d more"), Results.Num() - MaxRows),
					 FLinearColor(0.6f, 0.6f, 0.6f), BX + 22.0f, BY2, Font, Scale);
		}
		DrawText(TEXT("up / down select, enter plays, backspace deletes"),
				 FLinearColor(0.55f, 0.60f, 0.65f), BX + 14.0f, BY + BH - 24.0f,
				 Font, Scale);
	}

	FMorphRigFrameBreakdown::Current().Hud = (FPlatformTime::Seconds() - Start) * 1000.0;
}
