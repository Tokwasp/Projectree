FROM eclipse-temurin:21-jre
WORKDIR /app

# 현재 경로(./) 기준으로 build/libs 디렉토리 지정
COPY ./build/libs/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]