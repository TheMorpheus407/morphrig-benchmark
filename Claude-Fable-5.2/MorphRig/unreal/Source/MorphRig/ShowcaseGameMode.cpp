#include "ShowcaseGameMode.h"
#include "ShowcaseDirector.h"
#include "ShowcaseHUD.h"
#include "ShowcasePlayerController.h"
#include "Engine/World.h"

AShowcaseGameMode::AShowcaseGameMode()
{
	DefaultPawnClass = nullptr;
	PlayerControllerClass = AShowcasePlayerController::StaticClass();
	HUDClass = AShowcaseHUD::StaticClass();
}

void AShowcaseGameMode::StartPlay()
{
	GetWorld()->SpawnActor<AShowcaseDirector>();
	Super::StartPlay();
}
